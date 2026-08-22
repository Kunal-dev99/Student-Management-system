'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  rawLogin,
  rawLogout,
  rawRefresh,
  setAccessToken,
  setOnAuthFailure,
  setRefreshHandler,
} from '@/shared/api/client'

export interface Principal {
  authenticated: boolean
  userId: string | null
  email: string | null
  personId: string | null
  roles: string[]
  permissions: string[]
}

interface AuthState {
  principal: Principal | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  hasPermission: (code: string) => boolean
}

const AuthCtx = createContext<AuthState | null>(null)

// Refresh token persisted so a page reload can silently re-authenticate (arch §14.1
// "refresh handled silently"). Access token stays in memory only. Production hardening:
// move the refresh token to an httpOnly cookie (tracked as a follow-up).
const REFRESH_KEY = 'pgr_refresh'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [loading, setLoading] = useState(true)
  const refreshToken = useRef<string | null>(null)

  const loadMe = useCallback(async () => {
    const me = await api.get<Principal>('/me')
    setPrincipal(me)
  }, [])

  const doRefresh = useCallback(async (): Promise<string | null> => {
    const rt = refreshToken.current ?? (typeof window !== 'undefined' ? localStorage.getItem(REFRESH_KEY) : null)
    if (!rt) return null
    const tokens = await rawRefresh(rt)
    if (!tokens) return null
    setAccessToken(tokens.accessToken)
    refreshToken.current = tokens.refreshToken
    try { localStorage.setItem(REFRESH_KEY, tokens.refreshToken) } catch {}
    return tokens.accessToken
  }, [])

  const logout = useCallback(() => {
    // Best-effort server-side revocation before dropping local tokens (arch §12.1).
    const rt = refreshToken.current ?? (typeof window !== 'undefined' ? localStorage.getItem(REFRESH_KEY) : null)
    if (rt) void rawLogout(rt)
    setAccessToken(null)
    refreshToken.current = null
    try { localStorage.removeItem(REFRESH_KEY) } catch {}
    setPrincipal(null)
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await rawLogin(email, password)
      setAccessToken(tokens.accessToken)
      refreshToken.current = tokens.refreshToken
      try { localStorage.setItem(REFRESH_KEY, tokens.refreshToken) } catch {}
      await loadMe()
    },
    [loadMe],
  )

  // Wire the client's 401-recovery to this provider.
  useEffect(() => {
    setRefreshHandler(doRefresh)
    setOnAuthFailure(() => {
      setAccessToken(null)
      refreshToken.current = null
      try { localStorage.removeItem(REFRESH_KEY) } catch {}
      setPrincipal(null)
    })
    return () => {
      setRefreshHandler(null)
      setOnAuthFailure(null)
    }
  }, [doRefresh])

  // On first load, try to silently restore a session from the stored refresh token.
  useEffect(() => {
    let active = true
    ;(async () => {
      const token = await doRefresh()
      if (active && token) {
        try { await loadMe() } catch { /* fall through to unauthenticated */ }
      }
      if (active) setLoading(false)
    })()
    return () => { active = false }
  }, [doRefresh, loadMe])

  const hasPermission = useCallback(
    (code: string) => !!principal?.permissions.includes(code),
    [principal],
  )

  return (
    <AuthCtx.Provider value={{ principal, loading, login, logout, hasPermission }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
