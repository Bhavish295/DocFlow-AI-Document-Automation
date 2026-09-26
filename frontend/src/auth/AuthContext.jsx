import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  clearAuth,
  fetchCurrentUser,
  getStoredToken,
  getStoredUser,
  loginRequest,
  storeAuth,
} from '../services/authApi'
import { roleHasPermission } from '../auth/permissions'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => getStoredToken())
  const [user, setUser] = useState(() => getStoredUser())
  const [loading, setLoading] = useState(Boolean(getStoredToken()))
  const [error, setError] = useState('')

  const logout = useCallback(() => {
    clearAuth()
    setToken(null)
    setUser(null)
    setError('')
  }, [])

  useEffect(() => {
    let cancelled = false
    async function hydrate() {
      if (!token) {
        setLoading(false)
        return
      }
      try {
        const me = await fetchCurrentUser(token)
        if (!cancelled) {
          setUser(me)
          storeAuth(token, me)
        }
      } catch {
        if (!cancelled) {
          logout()
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    hydrate()
    return () => {
      cancelled = true
    }
  }, [token, logout])

  const login = useCallback(async (username, password) => {
    setError('')
    const result = await loginRequest(username, password)
    storeAuth(result.access_token, result.user)
    setToken(result.access_token)
    setUser(result.user)
    return result.user
  }, [])

  const can = useCallback(
    (permission) => roleHasPermission(user?.role, permission),
    [user],
  )

  const value = useMemo(
    () => ({
      token,
      user,
      loading,
      error,
      setError,
      login,
      logout,
      can,
      isAuthenticated: Boolean(token && user),
      isAdmin: user?.role === 'admin',
    }),
    [token, user, loading, error, login, logout, can],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
