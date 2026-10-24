import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const STATS = [
    { icon: '👥', label: 'Active Users', value: '12,400+' },
    { icon: '📊', label: 'Markets Live', value: '48' },
    { icon: '💰', label: 'Volume Traded', value: '₹2.4Cr+' },
    { icon: '🏆', label: 'Payouts Made', value: '₹1.8Cr+' },
]

const HOW_IT_WORKS = [
    { step: '1', icon: '💰', title: 'Add Money', desc: 'Deposit ₹500–₹5000 via UPI, Card or NetBanking instantly.' },
    { step: '2', icon: '📊', title: 'Pick a Market', desc: 'Browse markets on Cricket, Politics, Finance & more.' },
    { step: '3', icon: '🎯', title: 'Stake Your Side', desc: 'Choose YES or NO. The smarter side wins.' },
    { step: '4', icon: '🏆', title: 'Get Paid', desc: 'Correct predictions pay up to 1.5× your stake. Auto-credited.' },
]

const FEATURED_MARKETS = [
    { id: '1', title: 'Will India win the 3rd Test vs Australia?', category: 'cricket', yesPercent: 68, volume: '1,24,500' },
    { id: '2', title: 'Will RBI cut rates in December 2026?', category: 'finance', yesPercent: 41, volume: '87,200' },
    { id: '3', title: 'Will BJP win the Delhi elections?', category: 'politics', yesPercent: 55, volume: '2,10,000' },
]

export default function Landing() {
    const { user } = useAuth()

    return (
        <div className="landing">
            {/* Hero */}
            <section className="hero">
                <div className="hero-content">
                    <div className="hero-badge">🇮🇳 India's #1 Prediction Market</div>
                    <h1 className="hero-title">
                        Predict. Stake. <span className="gradient-text">Win in ₹.</span>
                    </h1>
                    <p className="hero-sub">
                        Trade on real-world events — Cricket, Politics, Finance & more.
                        The smarter your prediction, the bigger your payout.
                    </p>
                    <div className="hero-actions">
                        {user ? (
                            <Link to="/markets" className="btn-primary btn-large">Browse Markets →</Link>
                        ) : (
                            <>
                                <Link to="/register" className="btn-primary btn-large">Start Predicting Free →</Link>
                                <Link to="/login" className="btn-secondary btn-large">Login</Link>
                            </>
                        )}
                    </div>
                </div>
                <div className="hero-visual">
                    <div className="hero-card floating">
                        <div className="hero-market-preview">
                            <p>🏏 Will India win vs AUS?</p>
                            <div className="hero-odds-bar">
                                <div style={{ width: '68%', background: '#22c55e' }} />
                                <div style={{ width: '32%', background: '#ef4444' }} />
                            </div>
                            <div className="hero-odds-labels">
                                <span className="yes-col">YES 68%</span>
                                <span className="no-col">NO 32%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Stats */}
            <section className="stats-section">
                {STATS.map(s => (
                    <div key={s.label} className="stat-pill">
                        <span className="stat-icon">{s.icon}</span>
                        <div>
                            <div className="stat-num">{s.value}</div>
                            <div className="stat-lbl">{s.label}</div>
                        </div>
                    </div>
                ))}
            </section>

            {/* How it works */}
            <section className="how-section">
                <h2>How PredictIN Works</h2>
                <div className="how-grid">
                    {HOW_IT_WORKS.map(h => (
                        <div key={h.step} className="how-card">
                            <div className="how-icon">{h.icon}</div>
                            <div className="how-step">Step {h.step}</div>
                            <h3>{h.title}</h3>
                            <p>{h.desc}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* Featured Markets */}
            <section className="featured-section">
                <div className="featured-header">
                    <h2>🔥 Hot Markets</h2>
                    <Link to="/markets" className="see-all">See all →</Link>
                </div>
                <div className="featured-grid">
                    {FEATURED_MARKETS.map(m => (
                        <Link key={m.id} to="/markets" className="featured-card">
                            <span className="category-badge">{m.category}</span>
                            <h3>{m.title}</h3>
                            <div className="odds-bar">
                                <div className="odds-yes" style={{ width: `${m.yesPercent}%` }} />
                                <div className="odds-no" style={{ width: `${100 - m.yesPercent}%` }} />
                            </div>
                            <div className="odds-labels">
                                <span className="yes-label">YES {m.yesPercent}%</span>
                                <span className="no-label">NO {100 - m.yesPercent}%</span>
                            </div>
                            <span className="market-vol-sm">₹{m.volume} vol</span>
                        </Link>
                    ))}
                </div>
            </section>

            {/* CTA */}
            <section className="cta-section">
                <h2>Ready to make your prediction?</h2>
                <p>Join 12,000+ Indians already trading on PredictIN</p>
                <Link to="/register" className="btn-primary btn-large">Create Free Account →</Link>
            </section>
        </div>
    )
}
