import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Portfolio() {
    const { API } = useAuth()
    const [orders, setOrders] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        axios.get(`${API}/api/orders/my`).then(r => setOrders(r.data)).finally(() => setLoading(false))
    }, [])

    const active = orders.filter(o => o.status === 'active')
    const settled = orders.filter(o => o.status !== 'active')
    const totalInvested = active.reduce((s, o) => s + o.stake, 0)
    const totalWon = settled.filter(o => o.status === 'won').reduce((s, o) => s + (o.payout || 0), 0)
    const totalLost = settled.filter(o => o.status === 'lost').reduce((s, o) => s + o.stake, 0)
    const netProfit = settled.filter(o => o.status === 'won').reduce((s, o) => s + (o.payout || 0) - o.stake, 0) - totalLost

    const StatusBadge = ({ status }) => {
        const colors = { active: 'blue', won: 'green', lost: 'red', refunded: 'gray' }
        const icons = { active: '🔵', won: '🏆', lost: '❌', refunded: '↩️' }
        return <span className={`order-status status-${colors[status]}`}>{icons[status]} {status}</span>
    }

    const OrderRow = ({ order }) => (
        <div className="order-row">
            <div className="order-market">
                <Link to={`/markets/${order.market_id}`}>{order.markets?.title || 'Market'}</Link>
                <span className={`side-pill ${order.side}`}>{order.side.toUpperCase()}</span>
            </div>
            <div className="order-numbers">
                <span>Staked: <strong>₹{order.stake.toLocaleString('en-IN')}</strong></span>
                {order.payout > 0 && <span className="payout-green">Payout: <strong>₹{order.payout.toLocaleString('en-IN')}</strong></span>}
            </div>
            <StatusBadge status={order.status} />
            <span className="order-date">{new Date(order.created_at).toLocaleDateString('en-IN')}</span>
        </div>
    )

    if (loading) return <div className="page"><div className="loading-spinner" /></div>

    return (
        <div className="page portfolio-page">
            <div className="page-header"><h1>💼 My Portfolio</h1></div>

            <div className="portfolio-stats">
                <div className="stat-card">
                    <span className="stat-label">Active Positions</span>
                    <span className="stat-value blue">{active.length}</span>
                    <span className="stat-sub">₹{totalInvested.toLocaleString('en-IN')} at risk</span>
                </div>
                <div className="stat-card">
                    <span className="stat-label">Total Won</span>
                    <span className="stat-value green">₹{totalWon.toLocaleString('en-IN')}</span>
                </div>
                <div className="stat-card">
                    <span className="stat-label">Total Lost</span>
                    <span className="stat-value red">₹{totalLost.toLocaleString('en-IN')}</span>
                </div>
                <div className="stat-card">
                    <span className="stat-label">Net P&L</span>
                    <span className={`stat-value ${netProfit >= 0 ? 'green' : 'red'}`}>
                        {netProfit >= 0 ? '+' : ''}₹{netProfit.toLocaleString('en-IN')}
                    </span>
                </div>
            </div>

            {active.length > 0 && (
                <div className="order-section">
                    <h2>Active Positions</h2>
                    {active.map(o => <OrderRow key={o.id} order={o} />)}
                </div>
            )}

            {settled.length > 0 && (
                <div className="order-section">
                    <h2>Settled</h2>
                    {settled.map(o => <OrderRow key={o.id} order={o} />)}
                </div>
            )}

            {orders.length === 0 && (
                <div className="empty-state">
                    <div className="empty-icon">🎯</div>
                    <p>No positions yet. <Link to="/markets">Browse markets →</Link></p>
                </div>
            )}
        </div>
    )
}
