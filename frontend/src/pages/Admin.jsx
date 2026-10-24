import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'

const CATEGORIES = ['cricket', 'politics', 'finance', 'entertainment', 'other']

export default function Admin() {
    const { API, user } = useAuth()
    const navigate = useNavigate()
    const [stats, setStats] = useState(null)
    const [markets, setMarkets] = useState([])
    const [form, setForm] = useState({ title: '', description: '', category: 'cricket', end_date: '', cricapi_match_id: '' })
    const [resolveData, setResolveData] = useState({})
    const [msg, setMsg] = useState('')

    useEffect(() => {
        if (!user?.is_admin) { navigate('/markets'); return }
        fetchStats(); fetchMarkets()
    }, [user])

    const fetchStats = async () => {
        try { const { data } = await axios.get(`${API}/api/admin/stats`); setStats(data) } catch { }
    }
    const fetchMarkets = async () => {
        try { const { data } = await axios.get(`${API}/api/markets`, { params: { status: 'all' } }); setMarkets(data.filter(m => ['open', 'closed'].includes(m.status))) } catch { }
    }

    const createMarket = async (e) => {
        e.preventDefault()
        try {
            await axios.post(`${API}/api/markets`, form)
            setMsg('✅ Market created!'); fetchMarkets()
            setForm({ title: '', description: '', category: 'cricket', end_date: '', cricapi_match_id: '' })
        } catch (err) { setMsg('❌ ' + (err.response?.data?.detail || 'Failed')) }
    }

    const resolveMarket = async (marketId) => {
        const outcome = resolveData[marketId]
        if (!outcome) { alert('Select YES or NO first'); return }
        try {
            const { data } = await axios.post(`${API}/api/markets/${marketId}/resolve`, { outcome })
            setMsg(`✅ Market resolved as ${outcome.toUpperCase()}. Platform earned ₹${data.platform_revenue}`)
            fetchMarkets()
        } catch (err) { setMsg('❌ ' + (err.response?.data?.detail || 'Failed')) }
    }

    return (
        <div className="page admin-page">
            <div className="page-header"><h1>⚙️ Admin Dashboard</h1></div>

            {stats && (
                <div className="admin-stats">
                    {[
                        { label: 'Total Users', value: stats.total_users, icon: '👥' },
                        { label: 'Total Markets', value: stats.total_markets, icon: '📊' },
                        { label: 'Total Volume', value: `₹${Number(stats.total_volume).toLocaleString('en-IN')}`, icon: '📦' },
                        { label: 'Platform Revenue', value: `₹${Number(stats.platform_revenue).toLocaleString('en-IN')}`, icon: '💰' },
                    ].map(s => (
                        <div key={s.label} className="admin-stat-card">
                            <span className="stat-icon">{s.icon}</span>
                            <span className="stat-value">{s.value}</span>
                            <span className="stat-label">{s.label}</span>
                        </div>
                    ))}
                </div>
            )}

            <div className="admin-sections">
                <div className="admin-section">
                    <h2>Create Market</h2>
                    {msg && <div className="alert">{msg}</div>}
                    <form onSubmit={createMarket} className="admin-form">
                        <div className="form-group">
                            <label>Title</label>
                            <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Will India win today's match?" required />
                        </div>
                        <div className="form-group">
                            <label>Description</label>
                            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={2} />
                        </div>
                        <div className="form-row">
                            <div className="form-group">
                                <label>Category</label>
                                <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
                                    {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                                </select>
                            </div>
                            <div className="form-group">
                                <label>End Date</label>
                                <input type="datetime-local" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} required />
                            </div>
                        </div>
                        <div className="form-group">
                            <label>CricAPI Match ID (optional reference)</label>
                            <input value={form.cricapi_match_id} onChange={e => setForm({ ...form, cricapi_match_id: e.target.value })} placeholder="Leave blank for manual" />
                        </div>
                        <button type="submit" className="btn-primary">Create Market</button>
                    </form>
                </div>

                <div className="admin-section">
                    <h2>Markets Awaiting Settlement</h2>
                    <div className="admin-markets-list">
                        {markets.map(m => (
                            <div key={m.id} className="admin-market-row">
                                <div>
                                    <strong>{m.title}</strong>
                                    <span className="market-vol">{m.status}</span>
                                    <span className="market-vol">₹{Number(m.total_volume).toLocaleString('en-IN')} vol</span>
                                </div>
                                <div className="resolve-controls">
                                    <select value={resolveData[m.id] || ''}
                                        onChange={e => setResolveData({ ...resolveData, [m.id]: e.target.value })}>
                                        <option value="">Pick outcome</option>
                                        <option value="yes">YES wins</option>
                                        <option value="no">NO wins</option>
                                    </select>
                                    <button className="btn-resolve" onClick={() => resolveMarket(m.id)}>Resolve</button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}
