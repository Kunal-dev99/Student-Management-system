/**
 * Thin API client for the PGR backend (arch §11, §14.1).
 *
 * - All data access goes through `/api/v1` (proxied to FastAPI in dev via next.config).
 * - Understands the list envelope `{ data, page }` and the error envelope
 *   `{ error: { code, message, requestId, details } }`.
 * - Access token held in memory only (§14.1). On 401 it asks the registered refresh
 *   handler for a new token once, then retries.
 */

export const API_BASE = '/api/v1'

let accessToken: string | null = null
export function setAccessToken(token: string | null) {
  accessToken = token
}

// Registered by the auth layer so the client can recover from an expired access token.
let refreshHandler: (() => Promise<string | null>) | null = null
export function setRefreshHandler(fn: (() => Promise<string | null>) | null) {
  refreshHandler = fn
}
let onAuthFailure: (() => void) | null = null
export function setOnAuthFailure(fn: (() => void) | null) {
  onAuthFailure = fn
}

export interface ApiErrorBody {
  code: string
  message: string
  requestId: string
  details: unknown[]
}

export class ApiError extends Error {
  code: string
  requestId: string
  status: number
  details: unknown[]
  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.requestId = body.requestId
    this.details = body.details ?? []
  }
}

export interface Page {
  limit: number
  nextCursor: string | null
  total: number | null
}
export interface ListResponse<T> {
  data: T[]
  page: Page
}

async function raw(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}

async function request<T>(path: string, init: RequestInit = {}, _retried = false): Promise<T> {
  let res = await raw(path, init, accessToken)

  // Access token expired — try one silent refresh, then retry the original request.
  if (res.status === 401 && !_retried && refreshHandler) {
    const newToken = await refreshHandler()
    if (newToken) {
      res = await raw(path, init, newToken)
    }
  }

  if (res.status === 204) return undefined as T
  const payload = await res.json().catch(() => null)

  if (!res.ok) {
    const body: ApiErrorBody = payload?.error ?? {
      code: 'internal_error',
      message: res.statusText || 'Request failed',
      requestId: res.headers.get('X-Request-ID') ?? 'unknown',
      details: [],
    }
    if (res.status === 401 && onAuthFailure) onAuthFailure()
    throw new ApiError(res.status, body)
  }
  return payload as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

// Direct login/refresh calls that must NOT go through the 401-refresh loop.
export async function rawLogin(email: string, password: string) {
  const res = await raw('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }, null)
  const payload = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, payload?.error ?? { code: 'error', message: 'Login failed', requestId: 'unknown', details: [] })
  return payload as { accessToken: string; refreshToken: string; tokenType: string }
}

export async function rawRefresh(refreshToken: string) {
  const res = await raw('/auth/refresh', { method: 'POST', body: JSON.stringify({ refreshToken }) }, null)
  if (!res.ok) return null
  return (await res.json()) as { accessToken: string; refreshToken: string }
}

// Download an authenticated file (e.g. an export CSV) and trigger a browser save.
export async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await raw(path, {}, accessToken)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Upload a file via multipart/form-data. Does NOT set Content-Type (the browser adds the
// multipart boundary). Retries once through the refresh handler on a 401, like `request`.
export async function uploadFile<T>(path: string, form: FormData): Promise<T> {
  const doFetch = (token: string | null) => {
    const headers = new Headers({ Accept: 'application/json' })
    if (token) headers.set('Authorization', `Bearer ${token}`)
    return fetch(`${API_BASE}${path}`, { method: 'POST', body: form, headers })
  }
  let res = await doFetch(accessToken)
  if (res.status === 401 && refreshHandler) {
    const newToken = await refreshHandler()
    if (newToken) res = await doFetch(newToken)
  }
  const payload = await res.json().catch(() => null)
  if (!res.ok) {
    const body: ApiErrorBody = payload?.error ?? {
      code: 'error', message: res.statusText || 'Upload failed',
      requestId: res.headers.get('X-Request-ID') ?? 'unknown', details: [],
    }
    if (res.status === 401 && onAuthFailure) onAuthFailure()
    throw new ApiError(res.status, body)
  }
  return payload as T
}

// Best-effort server-side revocation of a refresh token (logout). Never throws.
export async function rawLogout(refreshToken: string): Promise<void> {
  try {
    await raw('/auth/logout', { method: 'POST', body: JSON.stringify({ refreshToken }) }, null)
  } catch {
    /* logout is best-effort; the client drops its tokens regardless */
  }
}

// Password reset (unauthenticated). Both always resolve; the API never reveals account state.
export async function rawPasswordResetRequest(email: string): Promise<void> {
  await raw('/auth/password-reset/request', { method: 'POST', body: JSON.stringify({ email }) }, null)
}
export async function rawPasswordResetConfirm(token: string, newPassword: string): Promise<Response> {
  return raw('/auth/password-reset/confirm', { method: 'POST', body: JSON.stringify({ token, newPassword }) }, null)
}

// Health lives outside /api/v1 (arch §18). Used by the connectivity banner.
export async function getHealth(): Promise<{ status: string; checks?: Record<string, string> }> {
  const res = await fetch('/health/ready')
  return res.json()
}
