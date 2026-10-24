import React, { useEffect, useState, useRef } from 'react'
import axios from 'axios'
import { useAuth } from '../context/AuthContext'

const DEPOSIT_AMOUNTS = [500, 1000, 2000, 5000]

export default function Wallet() {
    const { API, user, updateBalance } = useAuth()
    const balance = user?.wallet_balance ?? 0
    const [transactions, setTransactions] = useState([])
    const [loading, setLoading] = useState(true)
    const [depositing, setDepositing] = useState(false)
    const [message, setMessage] = useState(null)

    // Decentro UPI Modal State
    const [upiModalData, setUpiModalData] = useState(null)
    const [upiStatus, setUpiStatus] = useState('pending') // 'pending' | 'checking' | 'completed' | 'failed'
    const [copied, setCopied] = useState(false)
    const pollIntervalRef = useRef(null)

    useEffect(() => {
        fetchWallet()
        return () => stopPolling()
    }, [])

    const fetchWallet = async () => {
        try {
            const { data } = await axios.get(`${API}/api/wallet/balance`)
            updateBalance(data.balance)
            setTransactions(data.transactions || [])
            return data
        } catch (err) {
            setMessage({ type: 'error', text: err.response?.data?.detail || 'Could not load your wallet.' })
            return null
        } finally {
            setLoading(false)
        }
    }

    const stopPolling = () => {
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
        }
    }

    const startPolling = (referenceId) => {
        stopPolling()
        pollIntervalRef.current = setInterval(async () => {
            try {
                const { data } = await axios.get(`${API}/api/wallet/deposit/status/${referenceId}`)
                if (data.status === 'completed') {
                    stopPolling()
                    setUpiStatus('completed')
                    await fetchWallet()
                    setTimeout(() => {
                        closeUpiModal()
                        setMessage({ type: 'success', text: `₹${data.amount || 'funds'} successfully credited to your wallet!` })
                    }, 2200)
                } else if (data.status === 'failed') {
                    stopPolling()
                    setUpiStatus('failed')
                }
            } catch (err) {
                // Keep polling silently during temporary network hiccups
            }
        }, 2500)
    }

    const closeUpiModal = () => {
        stopPolling()
        setUpiModalData(null)
        setUpiStatus('pending')
        setDepositing(false)
    }

    const checkStatusManually = async () => {
        if (!upiModalData?.reference_id) return
        setUpiStatus('checking')
        try {
            const { data } = await axios.get(`${API}/api/wallet/deposit/status/${upiModalData.reference_id}`)
            if (data.status === 'completed') {
                stopPolling()
                setUpiStatus('completed')
                await fetchWallet()
                setTimeout(() => {
                    closeUpiModal()
                    setMessage({ type: 'success', text: `₹${data.amount || upiModalData.amount} credited to your wallet!` })
                }, 2000)
            } else if (data.status === 'failed') {
                setUpiStatus('failed')
            } else {
                setUpiStatus('pending')
                setMessage({ type: 'info', text: 'Payment is awaiting confirmation from your UPI app. Please approve the request.' })
            }
        } catch (err) {
            setUpiStatus('pending')
            setMessage({ type: 'error', text: err.response?.data?.detail || 'Status check failed. Please retry.' })
        }
    }

    const copyUpiLink = () => {
        const link = upiModalData?.payment_link || upiModalData?.upi_uri
        if (link) {
            navigator.clipboard.writeText(link)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        }
    }

    const handleDeposit = async (amount) => {
        setDepositing(true)
        setMessage(null)

        try {
            const { data } = await axios.post(`${API}/api/wallet/deposit`, { amount })

            // ── Decentro UPI Flow (Primary) ──────────────────────────────────
            if (data.gateway === 'decentro') {
                setUpiModalData(data)
                setUpiStatus('pending')
                startPolling(data.reference_id)
                return
            }

            // ── Razorpay Flow (Fallback) ────────────────────────────────────
            if (data.gateway === 'razorpay') {
                if (!window.Razorpay) {
                    setMessage({ type: 'error', text: 'Razorpay checkout script failed to load.' })
                    setDepositing(false)
                    return
                }

                const options = {
                    key: data.razorpay_key,
                    amount: data.amount_paise,
                    currency: data.currency,
                    name: 'PredictIN',
                    description: `Add ₹${amount} to wallet`,
                    order_id: data.razorpay_order_id,
                    handler: async (response) => {
                        try {
                            const { data: result } = await axios.post(`${API}/api/wallet/deposit/verify`, {
                                razorpay_order_id: response.razorpay_order_id,
                                razorpay_payment_id: response.razorpay_payment_id,
                                razorpay_signature: response.razorpay_signature,
                            })
                            setMessage({ type: 'success', text: 'Payment confirmed and your wallet has been credited.' })
                            await fetchWallet()
                        } catch (err) {
                            setMessage({ type: 'error', text: err.response?.data?.detail || 'Verification error' })
                        } finally {
                            setDepositing(false)
                        }
                    },
                    prefill: { name: user?.name, email: user?.email },
                    theme: { color: '#275d58' },
                    modal: { ondismiss: () => setDepositing(false) },
                }
                const rzp = new window.Razorpay(options)
                rzp.open()
                return
            }

            setMessage({ type: 'error', text: 'Unknown payment response from server.' })
            setDepositing(false)
        } catch (err) {
            setMessage({
                type: 'error',
                text: err.response?.data?.detail || 'Could not start payment. Please check server connection.',
            })
            setDepositing(false)
        }
    }

    const txnIcon = (type) => ({ deposit: '⬇️', trade: '📊', payout: '🏆', refund: '↩️', withdrawal: '⬆️' }[type] || '💸')

    // QR Image source: uses Decentro base64 QR if available, otherwise generates SVG QR via encoded upi_uri
    const qrImageSrc = upiModalData?.encoded_dynamic_qr_code
        ? `data:image/png;base64,${upiModalData.encoded_dynamic_qr_code}`
        : upiModalData?.upi_uri || upiModalData?.payment_link
        ? `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(upiModalData.upi_uri || upiModalData.payment_link)}`
        : null

    const psp = upiModalData?.psp_uri || {}

    return (
        <div className="page wallet-page">
            <div className="wallet-balance-card">
                <p className="balance-label">Available Balance</p>
                <h1 className="balance-amount">₹{Number(balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</h1>
                <p className="balance-sub">Your PredictIN wallet</p>
                {transactions.some(t => t.status === 'test_credit') && (
                    <p className="deposit-note">Includes test credit. No payment was received for this amount.</p>
                )}
            </div>

            {message && <div className={`alert alert-${message.type}`} role="status" aria-live="polite">{message.text}</div>}

            <div className="deposit-section">
                <h2>Add Money</h2>
                <div className="deposit-grid">
                    {DEPOSIT_AMOUNTS.map(amt => (
                        <button key={amt} className="deposit-btn" onClick={() => handleDeposit(amt)} disabled={depositing}>
                            <span className="deposit-amt">₹{amt.toLocaleString('en-IN')}</span>
                            <span className="deposit-sub">{depositing ? 'Preparing payment...' : 'Add via UPI'}</span>
                        </button>
                    ))}
                </div>
                <p className="deposit-note">⚡ Instant UPI Deposit via Google Pay, PhonePe, Paytm, BHIM, Cred · Powered by Decentro</p>
            </div>

            <div className="transactions-section">
                <h2>Transaction History</h2>
                {loading ? <div className="loading-spinner" /> : (
                    transactions.length === 0 ? (
                        <div className="empty-state"><div className="empty-icon">📭</div><p>No transactions yet</p></div>
                    ) : (
                        <div className="txn-list">
                            {transactions.map(t => (
                                <div key={t.id} className="txn-row">
                                    <span className="txn-icon">{txnIcon(t.type)}</span>
                                    <div className="txn-info">
                                        <span className="txn-type">{t.status === 'test_credit' ? 'Test credit' : t.type.charAt(0).toUpperCase() + t.type.slice(1)}</span>
                                        <span className="txn-note">{t.notes || t.reference_id || '—'}</span>
                                    </div>
                                    <div className="txn-right">
                                        <span className={`txn-amount ${t.amount > 0 ? 'positive' : 'negative'}`}>
                                            {t.amount > 0 ? '+' : ''}₹{Math.abs(t.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                        </span>
                                        <span className="txn-date">{new Date(t.created_at).toLocaleDateString('en-IN')}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )
                )}
            </div>

            {/* ── Decentro UPI Dynamic QR Modal ────────────────────────────── */}
            {upiModalData && (
                <div className="upi-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="upi-modal-title">
                    <div className="upi-modal-card">
                        <div className="upi-modal-header">
                            <div className="upi-modal-title">
                                <h3 id="upi-modal-title">Pay ₹{Number(upiModalData.amount).toLocaleString('en-IN')} via UPI</h3>
                                <p>Ref: {upiModalData.reference_id}</p>
                            </div>
                            <button className="upi-modal-close" onClick={closeUpiModal} aria-label="Close modal">×</button>
                        </div>

                        {upiStatus === 'completed' ? (
                            <div className="upi-success-card">
                                <span className="upi-success-icon">🎉</span>
                                <h4 className="upi-success-title">Payment Successful!</h4>
                                <p className="upi-success-sub">₹{upiModalData.amount} has been added to your PredictIN wallet.</p>
                                <button className="btn-primary btn-full" onClick={closeUpiModal}>Done</button>
                            </div>
                        ) : upiStatus === 'failed' ? (
                            <div className="upi-success-card">
                                <span className="upi-success-icon">❌</span>
                                <h4 className="upi-success-title" style={{ color: 'var(--rust)' }}>Payment Did Not Complete</h4>
                                <p className="upi-success-sub">The transaction expired or was declined by your bank.</p>
                                <div className="upi-modal-actions">
                                    <button className="btn-primary" onClick={() => handleDeposit(upiModalData.amount)}>Try Again</button>
                                    <button className="btn-secondary" onClick={closeUpiModal}>Close</button>
                                </div>
                            </div>
                        ) : (
                            <>
                                <div className="upi-pulse-status">
                                    <span className="upi-pulse-dot" />
                                    <span>{upiStatus === 'checking' ? 'Checking status with Decentro...' : 'Waiting for UPI authorization...'}</span>
                                </div>

                                {qrImageSrc && (
                                    <div className="upi-qr-box">
                                        <img
                                            src={qrImageSrc}
                                            alt="UPI Dynamic QR Code"
                                            className="upi-qr-img"
                                            onError={(e) => {
                                                const target = upiModalData?.upi_uri || upiModalData?.payment_link
                                                if (target && !e.currentTarget.dataset.triedFallback) {
                                                    e.currentTarget.dataset.triedFallback = 'true'
                                                    e.currentTarget.src = `https://quickchart.io/qr?size=240&text=${encodeURIComponent(target)}`
                                                }
                                            }}
                                        />
                                        <p className="upi-qr-label">Scan with Any UPI App</p>
                                        <p className="upi-qr-sub">Google Pay · PhonePe · Paytm · Cred · BHIM</p>
                                    </div>
                                )}

                                <div className="upi-app-buttons">
                                    {psp.gpay || upiModalData.upi_uri ? (
                                        <a href={psp.gpay || upiModalData.upi_uri} className="upi-app-btn">
                                            <span className="upi-app-icon">🟢</span>
                                            <span>Google Pay</span>
                                        </a>
                                    ) : null}
                                    {psp.phonepe || upiModalData.upi_uri ? (
                                        <a href={psp.phonepe || upiModalData.upi_uri} className="upi-app-btn">
                                            <span className="upi-app-icon">🟣</span>
                                            <span>PhonePe</span>
                                        </a>
                                    ) : null}
                                    {psp.paytm || upiModalData.upi_uri ? (
                                        <a href={psp.paytm || upiModalData.upi_uri} className="upi-app-btn">
                                            <span className="upi-app-icon">🔵</span>
                                            <span>Paytm</span>
                                        </a>
                                    ) : null}
                                </div>

                                {upiModalData.payment_link && (
                                    <div style={{ marginBottom: '14px', textAlign: 'center' }}>
                                        <a
                                            href={upiModalData.payment_link}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="btn-secondary btn-full"
                                            style={{ display: 'inline-block', textAlign: 'center', padding: '10px' }}
                                        >
                                            🔗 Open Decentro Payment Page ↗
                                        </a>
                                    </div>
                                )}

                                <div className="upi-modal-actions">
                                    <button
                                        className="btn-primary"
                                        onClick={checkStatusManually}
                                        disabled={upiStatus === 'checking'}
                                    >
                                        {upiStatus === 'checking' ? 'Verifying...' : 'I have Paid (Verify)'}
                                    </button>
                                    <button className="btn-secondary" onClick={copyUpiLink}>
                                        {copied ? '✓ Copied' : 'Copy Link'}
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
