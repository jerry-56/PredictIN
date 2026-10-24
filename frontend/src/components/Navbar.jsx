import React from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Navbar() {
    const { user, logout } = useAuth()
    const navigate = useNavigate()
    const location = useLocation()

    const handleLogout = () => { logout(); navigate('/') }

    const navLinks = [
        { to: '/markets', label: '📊 Markets' },
        { to: '/portfolio', label: '💼 Portfolio' },
        { to: '/wallet', label: '💰 Wallet' },
    ]

    return (
        <nav className="navbar">
            <Link to="/" className="navbar-brand">
                <span className="brand-icon">🏆</span>
                <span className="brand-name">PredictIN</span>
            </Link>

            <div className="navbar-links">
                {user && navLinks.map(l => (
                    <Link key={l.to} to={l.to} className={`nav-link ${location.pathname === l.to ? 'active' : ''}`}>
                        {l.label}
                    </Link>
                ))}
                {user?.is_admin && (
                    <Link to="/admin" className={`nav-link admin-link ${location.pathname === '/admin' ? 'active' : ''}`}>
                        ⚙️ Admin
                    </Link>
                )}
            </div>

            <div className="navbar-right">
                {user ? (
                    <>
                        <div className="wallet-pill">
                            ₹{Number(user.wallet_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>
                        <div className="user-menu">
                            <span className="user-name">{user.name}</span>
                            <button className="btn-logout" onClick={handleLogout}>Logout</button>
                        </div>
                    </>
                ) : (
                    <div className="auth-buttons">
                        <Link to="/login" className="btn-secondary">Login</Link>
                        <Link to="/register" className="btn-primary">Sign Up</Link>
                    </div>
                )}
            </div>
        </nav>
    )
}
