import React, { useEffect, useState } from 'react'
import axios from 'axios'
import MarketCard from '../components/MarketCard'
import { useAuth } from '../context/AuthContext'

const CATEGORIES = ['all', 'cricket', 'politics', 'finance', 'entertainment', 'other']

export default function Markets() {
    const { API } = useAuth()
    const [markets, setMarkets] = useState([])
    const [category, setCategory] = useState('all')
    const [search, setSearch] = useState('')
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchMarkets = async () => {
            setLoading(true)
            try {
                const params = category !== 'all' ? { category } : {}
                const { data } = await axios.get(`${API}/api/markets`, { params })
                setMarkets(data)
            } catch { setMarkets([]) }
            setLoading(false)
        }
        fetchMarkets()
    }, [category])

    const filtered = markets.filter(m =>
        m.title.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div className="page markets-page">
            <div className="page-header">
                <h1>📊 All Markets</h1>
                <p>Pick your side. Make your prediction.</p>
            </div>

            <div className="markets-controls">
                <input className="search-input" placeholder="🔍 Search markets..."
                    value={search} onChange={e => setSearch(e.target.value)} />
                <div className="category-tabs">
                    {CATEGORIES.map(c => (
                        <button key={c} className={`category-tab ${category === c ? 'active' : ''}`}
                            onClick={() => setCategory(c)}>
                            {c.charAt(0).toUpperCase() + c.slice(1)}
                        </button>
                    ))}
                </div>
            </div>

            {loading ? (
                <div className="loading-grid">
                    {[...Array(6)].map((_, i) => <div key={i} className="skeleton-card" />)}
                </div>
            ) : filtered.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-icon">🔮</div>
                    <p>No markets found. Check back soon!</p>
                </div>
            ) : (
                <div className="markets-grid">
                    {filtered.map(m => <MarketCard key={m.id} market={m} />)}
                </div>
            )}
        </div>
    )
}
