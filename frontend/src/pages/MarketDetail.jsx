import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import axios from 'axios'
import { useAuth } from '../context/AuthContext'
import { useSocket } from '../context/SocketContext'
import { estimatePayout } from '../utils/payout'

export default function MarketDetail() {
    const { id } = useParams()
    const { API, user, refreshBalance } = useAuth()
    const { subscribe, unsubscribe } = useSocket()
    const navigate = useNavigate()

    const [market, setMarket] = useState(null)
    const [stake, setStake] = useState('')
    const [side, setSide] = useState(null)
    const [loading, setLoading] = useState(true)
    const [tradeLoading, setTradeLoading] = useState(false)
    const [message, setMessage] = useState(null)
    const [userSide, setUserSide] = useState(null) // existing side if any

    useEffect(() => {
        fetchMarket()
        if (user) checkExistingOrder()
        const cleanup = subscribe(id, handleWsMessage)
        return () => { if (cleanup) cleanup(); unsubscribe(id) }
    }, [id])

    const fetchMarket = async () => {
        try {
            const { data } = await axios.get(`${API}/api/markets/${id}`)
            setMarket(data)
        } catch { navigate('/markets') }
        setLoading(false)
    }

    const checkExistingOrder = async () => {
        try {
            const { data } = await axios.get(`${API}/api/orders/my`)
            const existing = data.find(o => o.market_id === id && o.status === 'active')
            if (existing) setUserSide(existing.side)
        } catch { }
    }

    const handleWsMessage = useCallback((msg) => {
        if (msg.type === 'odds_update' && msg.market_id === id) {
            setMarket(prev => prev ? {
                ...prev, yes_price: msg.yes_price, no_price: msg.no_price,
                yes_pool: msg.yes_pool, no_pool: msg.no_pool, total_volume: msg.total_volume
            } : prev)
        }
        if (msg.type === 'market_resolved' && msg.market_id === id) {
            setMarket(prev => prev ? { ...prev, status: 'resolved', outcome: msg.outcome } : prev)
        }
    }, [id])

    const placeBet = async () => {
        if (!user) { navigate('/login'); return }
        if (!side || !stake || Number(stake) < 10) {
            setMessage({ type: 'error', text: 'Select a side and enter at least ₹10' }); return
        }
        setTradeLoading(true); setMessage(null)
        try {
            const { data } = await axios.post(`${API}/api/orders/buy`, {
                market_id: id, side, stake: Number(stake)
            })
            setMessage({ type: 'success', text: data.message })
            setUserSide(side)
            setStake('')
            setMarket(prev => prev ? {
                ...prev,
                yes_price: data.yes_price, no_price: data.no_price,
                yes_pool: data.yes_pool, no_pool: data.no_pool,
                total_volume: data.total_volume,
            } : prev)
            await refreshBalance()
        } catch (err) {
            setMessage({ type: 'error', text: err.response?.data?.detail || 'Trade failed' })
        } finally { setTradeLoading(false) }
    }

    if (loading) return <div className="page"><div className="loading-spinner" /></div>
    if (!market) return null
    const isDemo = market.description?.startsWith('[DEMO]')

    const yesPercent = Math.round((market.yes_price ?? 0.5) * 100)
    const noPercent = 100 - yesPercent
    const stakeNum = Number(stake) || 0
    const estimate = estimatePayout({ stake: stakeNum, side, yesPool: market.yes_pool, noPool: market.no_pool })
    const money = value => `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

    const chartData = (market.price_history || []).map((p, i) => ({
        t: i + 1,
        YES: Math.round(p.yes_price * 100),
        NO: Math.round(p.no_price * 100),
    }))

    return (
        <div className="page market-detail-page">
            <div className="market-detail-header">
                <span className="category-badge">{market.category}</span>
                <span className={`status-badge status-${market.status}`}>{isDemo ? 'Demo · no stakes' : market.status}</span>
                <h1>{market.title}</h1>
                <p className="market-desc">{market.description}</p>
                <div className="market-stats-row">
                    <span>📦 ₹{Number(market.total_volume || 0).toLocaleString('en-IN')} volume</span>
                    <span>⏰ Ends {new Date(market.end_date).toLocaleDateString('en-IN')}</span>
                    {market.outcome && <span className="outcome-badge">Outcome: {market.outcome.toUpperCase()}</span>}
                </div>
            </div>

            <div className="detail-layout">
                {/* Left: Chart + Odds */}
                <div className="detail-left">
                    <div className="odds-display">
                        <div className="odd-box yes-box">
                            <span className="odd-label">YES</span>
                            <span className="odd-value">{yesPercent}%</span>
                            <span className="odd-pool">₹{Number(market.yes_pool || 0).toLocaleString('en-IN')}</span>
                        </div>
                        <div className="odds-bar large">
                            <div className="odds-yes" style={{ width: `${yesPercent}%` }} />
                            <div className="odds-no" style={{ width: `${noPercent}%` }} />
                        </div>
                        <div className="odd-box no-box">
                            <span className="odd-label">NO</span>
                            <span className="odd-value">{noPercent}%</span>
                            <span className="odd-pool">₹{Number(market.no_pool || 0).toLocaleString('en-IN')}</span>
                        </div>
                    </div>

                    {chartData.length > 1 && (
                        <div className="chart-container">
                            <h3>Price History</h3>
                            <ResponsiveContainer width="100%" height={200}>
                                <LineChart data={chartData}>
                                    <XAxis dataKey="t" hide />
                                    <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} width={40} />
                                    <Tooltip formatter={(v) => `${v}%`} />
                                    <Line type="monotone" dataKey="YES" stroke="#22c55e" strokeWidth={2} dot={false} />
                                    <Line type="monotone" dataKey="NO" stroke="#ef4444" strokeWidth={2} dot={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    )}
                </div>

                {/* Right: Trading Panel */}
                {isDemo && (
                    <div className="trading-panel">
                        <h3>Demo market</h3>
                        <p>This sample event is for checking the market display. Stakes and payouts are disabled.</p>
                    </div>
                )}
                {market.status === 'open' && !isDemo && (
                    <div className="trading-panel">
                        <h3>Place Your Stake</h3>
                        {userSide && (
                            <div className="alert alert-info">
                                You already have a <strong>{userSide.toUpperCase()}</strong> position. You can add more.
                            </div>
                        )}
                        <div className="side-selector">
                            <button
                                className={`side-btn yes-btn ${side === 'yes' ? 'selected' : ''} ${userSide === 'no' ? 'disabled' : ''}`}
                                onClick={() => userSide !== 'no' && setSide('yes')}
                                disabled={userSide === 'no'}>
                                ✅ YES — {yesPercent}%
                            </button>
                            <button
                                className={`side-btn no-btn ${side === 'no' ? 'selected' : ''} ${userSide === 'yes' ? 'disabled' : ''}`}
                                onClick={() => userSide !== 'yes' && setSide('no')}
                                disabled={userSide === 'yes'}>
                                ❌ NO — {noPercent}%
                            </button>
                        </div>

                        <div className="quick-stakes">
                            {[100, 500, 1000, 2000].map(amt => (
                                <button key={amt} className="quick-stake-btn" onClick={() => setStake(String(amt))}>₹{amt}</button>
                            ))}
                        </div>

                        <div className="form-group">
                            <label>Custom Amount (₹)</label>
                            <input type="number" min="10" max="50000" placeholder="Enter amount"
                                value={stake} onChange={e => setStake(e.target.value)} />
                        </div>

                        {estimate && (
                            <div className="payout-preview payout-breakdown" aria-live="polite">
                                <h4>{estimate.refund ? 'Estimated refund' : `Estimated payout if ${side.toUpperCase()} wins`}</h4>
                                <strong className="payout-value">{money(estimate.payout)}</strong>
                                <p className="payout-note">For this new {money(stakeNum)} stake only. Existing stakes are already included in the pool totals below.</p>
                                <dl>
                                    <div><dt>Total return / new stake</dt><dd>{(estimate.payout / stakeNum).toFixed(4)}×</dd></div>
                                    <div><dt>{side.toUpperCase()} pool after your stake</dt><dd>{money(estimate.winningPool)}</dd></div>
                                    <div><dt>Opposite pool</dt><dd>{money(estimate.losingPool)}</dd></div>
                                    <div><dt>Your share of the {side.toUpperCase()} pool</dt><dd>{(estimate.share * 100).toFixed(2)}%</dd></div>
                                    <div><dt>Winner profit pool</dt><dd>{money(estimate.profitPool)}</dd></div>
                                    <div><dt>Your estimated profit</dt><dd>{money(estimate.profit)}</dd></div>
                                    <div><dt>Stake returned</dt><dd>{money(stakeNum)}</dd></div>
                                </dl>
                                {estimate.refund ? (
                                    <p className="payout-note">Both sides need at least ₹100. If these pools remain at settlement, the market is voided and stakes are refunded with no profit.</p>
                                ) : (
                                    <>
                                        <p className="payout-note">{0.5 * estimate.winningPool <= 0.9 * estimate.losingPool
                                            ? 'The opposing pool supports the 50% profit cap: total return is up to 1.5× your stake.'
                                            : 'The opposing pool limits the profit: total return is below 1.5× your stake.'}</p>
                                        <p className="payout-note">Profit pool = smaller of 50% of the winning pool or 90% of the losing pool. Your profit = your share × profit pool, rounded down to the nearest paisa.</p>
                                        <p className="payout-note">Payout includes your stake. If your side loses, the payout is ₹0.</p>
                                    </>
                                )}
                                <p className="payout-note">Estimate uses current pools plus this stake. Final payout changes as others stake.</p>
                            </div>
                        )}

                        {message && <div className={`alert alert-${message.type}`}>{message.text}</div>}

                        <button className="btn-primary btn-full btn-trade" onClick={placeBet} disabled={tradeLoading || !side}>
                            {tradeLoading ? 'Placing...' : `Stake ₹${stakeNum || '—'} on ${side ? side.toUpperCase() : '—'}`}
                        </button>

                        {!user && <p className="login-prompt">You must <a href="/login">login</a> to stake</p>}
                    </div>
                )}

                {market.status === 'voided' && (
                    <div className="trading-panel resolved-panel">
                        <h3>Market voided — stakes refunded</h3>
                        <p>All stakes have been returned to their wallets. No profit or platform revenue was charged.</p>
                    </div>
                )}
                {market.status === 'resolved' && (
                    <div className="trading-panel resolved-panel">
                        <div className="resolved-outcome">
                            <span>{market.outcome === 'yes' ? '✅' : '❌'}</span>
                            <h3>Market Resolved</h3>
                            <p>Outcome: <strong>{market.outcome?.toUpperCase()}</strong></p>
                            <p className="resolved-note">Winners have been credited to their wallets.</p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
