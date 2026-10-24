import React from 'react'
import { Link } from 'react-router-dom'

const CATEGORY_ICONS = {
    cricket: '🏏', politics: '🏛️', finance: '📈', entertainment: '🎬', other: '🔮'
}

export default function MarketCard({ market }) {
    const yesPercent = Math.round((market.yes_price ?? 0.5) * 100)
    const noPercent = 100 - yesPercent
    const volume = Number(market.total_volume || 0)
    const isDemo = market.description?.startsWith('[DEMO]')

    return (
        <Link to={`/markets/${market.id}`} className="market-card">
            <div className="market-card-header">
                <span className="category-badge">
                    {CATEGORY_ICONS[market.category] || '🔮'} {market.category}
                </span>
                <span className={`status-badge status-${market.status}`}>{isDemo ? 'Demo' : market.status}</span>
            </div>

            <h3 className="market-title">{market.title}</h3>

            <div className="odds-bar-container">
                <div className="odds-bar">
                    <div className="odds-yes" style={{ width: `${yesPercent}%` }} />
                    <div className="odds-no" style={{ width: `${noPercent}%` }} />
                </div>
                <div className="odds-labels">
                    <span className="yes-label">YES {yesPercent}%</span>
                    <span className="no-label">NO {noPercent}%</span>
                </div>
            </div>

            <div className="market-meta">
                <span>📦 ₹{volume.toLocaleString('en-IN')} vol</span>
                <span>⏰ {new Date(market.end_date).toLocaleDateString('en-IN')}</span>
            </div>
        </Link>
    )
}
