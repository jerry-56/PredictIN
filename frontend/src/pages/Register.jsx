import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Register() {
    const { register } = useAuth()
    const navigate = useNavigate()
    const [form, setForm] = useState({ name: '', email: '', password: '' })
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (form.password.length < 6) { setError('Password must be at least 6 characters'); return }
        setLoading(true); setError('')
        try {
            const result = await register(form.name, form.email, form.password)
            if (result.confirmation_required) {
                setNotice('Check your email to confirm your account, then log in.')
            } else {
                navigate('/markets')
            }
        } catch (err) {
            setError(err.response?.data?.detail || 'Registration failed')
        } finally { setLoading(false) }
    }

    return (
        <div className="auth-page">
            <div className="auth-card">
                <div className="auth-logo">🏆</div>
                <h1 className="auth-title">Create account</h1>
                <p className="auth-sub">Start predicting. Start earning.</p>
                {error && <div className="alert alert-error">{error}</div>}
                {notice && <div className="alert">{notice}</div>}
                <form onSubmit={handleSubmit} className="auth-form">
                    <div className="form-group">
                        <label>Full Name</label>
                        <input type="text" placeholder="Rahul Sharma" value={form.name}
                            onChange={e => setForm({ ...form, name: e.target.value })} required />
                    </div>
                    <div className="form-group">
                        <label>Email</label>
                        <input type="email" placeholder="you@example.com" value={form.email}
                            onChange={e => setForm({ ...form, email: e.target.value })} required />
                    </div>
                    <div className="form-group">
                        <label>Password</label>
                        <input type="password" placeholder="Min 6 characters" value={form.password}
                            onChange={e => setForm({ ...form, password: e.target.value })} required />
                    </div>
                    <button type="submit" className="btn-primary btn-full" disabled={loading}>
                        {loading ? 'Creating account...' : 'Create Account →'}
                    </button>
                </form>
                <p className="auth-switch">Already have an account? <Link to="/login">Login</Link></p>
            </div>
        </div>
    )
}
