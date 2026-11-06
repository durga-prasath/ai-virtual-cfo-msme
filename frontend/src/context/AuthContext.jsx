import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authAPI } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)
  const [loading, setLoading] = useState(true)

  // Try to restore session from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) { setLoading(false); return }
    authAPI.me()
      .then(res => setUser(res.data))
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await authAPI.login({ email, password })
    localStorage.setItem('token', res.data.access_token)
    const me = await authAPI.me()
    setUser(me.data)
    return me.data
  }, [])

  const register = useCallback(async (formData) => {
    await authAPI.register(formData)
    return login(formData.email, formData.password)
  }, [login])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
