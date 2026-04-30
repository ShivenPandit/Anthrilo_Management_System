'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const RECONNECT_DELAY = 2000
const MAX_RECONNECT_DELAY = 30000
const MAX_RECONNECT_ATTEMPTS = 10
const HEARTBEAT_INTERVAL = 25000

interface WebSocketMessage {
    type: string
    data?: any
    message?: string
}

interface OrderNotification {
    count: number
    totalOrders: number
    totalRevenue: number
    orders?: any[]
}

function resolveWebSocketUrl(): string {
    if (process.env.NEXT_PUBLIC_WS_URL) {
        return process.env.NEXT_PUBLIC_WS_URL
    }

    if (process.env.NEXT_PUBLIC_API_URL) {
        try {
            const apiUrl = new URL(process.env.NEXT_PUBLIC_API_URL)
            const wsProtocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:'
            return `${wsProtocol}//${apiUrl.host}/api/v1/integrations/ws/sales`
        } catch {
            // Fall through to window-based fallback.
        }
    }

    if (typeof window !== 'undefined') {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        return `${wsProtocol}//${window.location.host}/api/v1/integrations/ws/sales`
    }

    return 'ws://127.0.0.1:8000/api/v1/integrations/ws/sales'
}

// Real-time dashboard updates via WebSocket.
// Auto-reconnects and pushes new data into the React Query cache.
export function useWebSocket() {
    const wsRef = useRef<WebSocket | null>(null)
    const reconnectAttemptsRef = useRef(0)
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>()
    const heartbeatTimerRef = useRef<ReturnType<typeof setInterval>>()
    const isMountedRef = useRef(false)
    const manualCloseRef = useRef(false)
    const queryClient = useQueryClient()
    const [isConnected, setIsConnected] = useState(false)
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
    const [newOrderNotification, setNewOrderNotification] = useState<OrderNotification | null>(null)

    const clearReconnectTimer = useCallback(() => {
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current)
            reconnectTimerRef.current = undefined
        }
    }, [])

    const clearHeartbeatTimer = useCallback(() => {
        if (heartbeatTimerRef.current) {
            clearInterval(heartbeatTimerRef.current)
            heartbeatTimerRef.current = undefined
        }
    }, [])

    const connect = useCallback(() => {
        // Don't connect during SSR or after unmount
        if (typeof window === 'undefined') return
        if (!isMountedRef.current) return
        if (manualCloseRef.current) return

        clearReconnectTimer()

        // Avoid duplicate connections (already open or in the process of connecting)
        const state = wsRef.current?.readyState
        if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) return

        // Stop trying after max attempts
        if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
            if (reconnectAttemptsRef.current === MAX_RECONNECT_ATTEMPTS) {
                console.warn('WebSocket: Max reconnection attempts reached. Backend may be offline.')
                reconnectAttemptsRef.current++ // prevent repeated warnings
            }
            return
        }

        try {
            const ws = new WebSocket(resolveWebSocketUrl())
            wsRef.current = ws

            ws.onopen = () => {
                if (!isMountedRef.current) { ws.close(); return }
                if (manualCloseRef.current) { ws.close(1000, 'manual close'); return }

                setIsConnected(true)
                reconnectAttemptsRef.current = 0
                console.log('WebSocket: Connected to sales feed')

                clearHeartbeatTimer()
                heartbeatTimerRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ action: 'ping' }))
                    }
                }, HEARTBEAT_INTERVAL)

                ws.send(JSON.stringify({ action: 'subscribe' }))
            }

            ws.onmessage = (event) => {
                if (!isMountedRef.current) return
                try {
                    const msg: WebSocketMessage = JSON.parse(event.data)
                    if (msg.type === 'today_sales' && msg.data) {
                        queryClient.setQueryData(['unicommerce-today'], msg.data)
                        setLastUpdate(new Date())
                    }
                    if (msg.type === 'sync_completed') {
                        queryClient.invalidateQueries({ queryKey: ['unicommerce-today'] })
                        queryClient.invalidateQueries({ queryKey: ['unicommerce-yesterday'] })
                        queryClient.invalidateQueries({ queryKey: ['unicommerce-last-7-days'] })
                        queryClient.invalidateQueries({ queryKey: ['unicommerce-channels'] })
                        setLastUpdate(new Date())
                    }
                    if (msg.type === 'new_order' && msg.data) {
                        setNewOrderNotification(msg.data)
                        setLastUpdate(new Date())
                    }
                } catch {
                    // Ignore malformed messages
                }
            }

            ws.onclose = () => {
                if (wsRef.current === ws) {
                    wsRef.current = null
                }
                clearHeartbeatTimer()

                // If the component has already unmounted, do not reschedule
                if (!isMountedRef.current) return
                if (manualCloseRef.current) return

                setIsConnected(false)

                if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttemptsRef.current += 1
                    const exponential = RECONNECT_DELAY * (2 ** (reconnectAttemptsRef.current - 1))
                    const jitter = Math.floor(Math.random() * 300)
                    const delay = Math.min(exponential, MAX_RECONNECT_DELAY) + jitter

                    if (reconnectAttemptsRef.current === 1) {
                        console.log('WebSocket: Connection closed. Will retry...')
                    }

                    clearReconnectTimer()
                    reconnectTimerRef.current = setTimeout(() => {
                        if (!isMountedRef.current || manualCloseRef.current) return
                        connect()
                    }, delay)
                } else {
                    console.warn('WebSocket: Unable to connect. Please ensure the backend is running and NEXT_PUBLIC_WS_URL is set correctly.')
                }
            }

            ws.onerror = () => {
                // Only log the first few errors; onerror is always followed by onclose
                if (reconnectAttemptsRef.current < 3) {
                    console.warn('WebSocket: Connection error — will retry automatically')
                }

                if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                    ws.close()
                }
            }
        } catch (error) {
            if (reconnectAttemptsRef.current < 3) {
                console.warn('WebSocket: Failed to create connection', error)
            }
        }
    }, [clearHeartbeatTimer, clearReconnectTimer, queryClient])

    useEffect(() => {
        isMountedRef.current = true
        manualCloseRef.current = false
        reconnectAttemptsRef.current = 0 // start fresh on each mount
        connect()

        return () => {
            isMountedRef.current = false
            manualCloseRef.current = true
            setIsConnected(false)
            clearReconnectTimer()
            clearHeartbeatTimer()

            // Close without triggering reconnect (onclose checks isMountedRef)
            if (wsRef.current) {
                if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
                    wsRef.current.close(1000, 'component unmount')
                }
                wsRef.current = null
            }
        }
    }, [clearHeartbeatTimer, clearReconnectTimer, connect])

    const requestRefresh = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ action: 'refresh' }))
        }
    }, [])

    const dismissNotification = useCallback(() => {
        setNewOrderNotification(null)
    }, [])

    return { isConnected, lastUpdate, requestRefresh, newOrderNotification, dismissNotification }
}
