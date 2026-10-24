import React, { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'

const AuthContext = createContext(null)
const API = import.meta.env.VITE_API_URL || 'http://localhost:7860'

export function AuthProvider({ children }) {
  const [user, setUser]   = useState(null)
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [loading, setLoading] = useState(true)

  const updateBalance = (balance) => {
    setUser(current => {
      if (!current) return current
      const updated = { ...current, wallet_balance: Number(balance) }
      localStorage.setItem('user', JSON.stringify(updated))
      return updated
    })
  }

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
      const stored = localStorage.getItem('user')
      if (stored) setUser(JSON.parse(stored))
      axios.get(`${API}/api/wallet/balance`, {
        headers: { Authorization: `Bearer ${token}` }
      }).then(({ data }) => updateBalance(data.balance)).catch(() => {})
    }
    setLoading(false)
  }, [])

  const login = async (email, password) => {
    const { data } = await axios.post(`${API}/api/auth/login`, { email, password })
    setToken(data.token)
    setUser(data.user)
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify(data.user))
    axios.defaults.headers.common['Authorization'] = `Bearer ${data.token}`
    return data.user
  }

  const register = async (name, email, password) => {
    const { data } = await axios.post(`${API}/api/auth/register`, { name, email, password })
    if (data.confirmation_required) return data
    setToken(data.token)
    setUser(data.user)
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify(data.user))
    axios.defaults.headers.common['Authorization'] = `Bearer ${data.token}`
    return data
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    delete axios.defaults.headers.common['Authorization']
  }

  const refreshBalance = async () => {
    try {
      const { data } = await axios.get(`${API}/api/wallet/balance`)
      updateBalance(data.balance)
      return data.balance
    } catch { return user?.wallet_balance || 0 }
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, refreshBalance, updateBalance, API }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
