import React, { createContext, useContext, useEffect, useRef } from 'react'

const SocketContext = createContext(null)
const WS_URL = (import.meta.env.VITE_WS_URL || import.meta.env.VITE_API_URL || 'http://localhost:7860').replace(/^http/, 'ws').replace(/\/$/, '')

export function SocketProvider({ children }) {
    const socketsRef = useRef({})

    const subscribe = (marketId, onMessage) => {
        if (socketsRef.current[marketId]) return
        const ws = new WebSocket(`${WS_URL}/ws/market/${marketId}`)
        ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)) } catch { } }
        let heartbeat
        ws.onopen = () => { heartbeat = setInterval(() => ws.readyState === 1 && ws.send('ping'), 30000) }
        ws.onclose = () => { clearInterval(heartbeat) }
        socketsRef.current[marketId] = ws
        return () => { ws.close(); delete socketsRef.current[marketId] }
    }

    const unsubscribe = (marketId) => {
        if (socketsRef.current[marketId]) {
            socketsRef.current[marketId].close()
            delete socketsRef.current[marketId]
        }
    }

    return (
        <SocketContext.Provider value={{ subscribe, unsubscribe }}>
            {children}
        </SocketContext.Provider>
    )
}

export const useSocket = () => useContext(SocketContext)
