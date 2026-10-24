import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
    const { login } = useAuth()
    const navigate = useNavigate()
    const [form, setForm] = useState({ email: '', password: '' })
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e) => {
        e.preventDefault()
        setLoading(true); setError('')
        try {
            await login(form.email, form.password)
            navigate('/markets')
        } catch (err) {
            setError(err.response?.data?.detail || 'Login failed')
        } finally { setLoading(false) }
    }

    return (
        <div className="auth-page">
            <div className="auth-card">
                <div className="auth-logo">🏆</div>
                <h1 className="auth-title">Welcome back</h1>
                <p className="auth-sub">Login to your PredictIN account</p>
                {error && <div className="alert alert-error">{error}</div>}
                <form onSubmit={handleSubmit} className="auth-form">
                    <div className="form-group">
                        <label>Email</label>
                        <input type="email" placeholder="you@example.com" value={form.email}
                            onChange={e => setForm({ ...form, email: e.target.value })} required />
                    </div>
                    <div className="form-group">
                        <label>Password</label>
                        <input type="password" placeholder="••••••••" value={form.password}
                            onChange={e => setForm({ ...form, password: e.target.value })} required />
                    </div>
                    <button type="submit" className="btn-primary btn-full" disabled={loading}>
                        {loading ? 'Logging in...' : 'Login →'}
                    </button>
                </form>
                <p className="auth-switch">Don't have an account? <Link to="/register">Sign up free</Link></p>
            </div>
        </div>
    )
}
