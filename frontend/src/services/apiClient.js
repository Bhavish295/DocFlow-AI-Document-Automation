import { apiV1Url } from '../config'
import { clearAuth, getStoredToken } from './authApi'

export async function parseApiError(response) {
  let detail = `Request failed with status ${response.status}`
  try {
    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      const payload = await response.json()
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        detail = payload.detail
      } else if (Array.isArray(payload.detail)) {
        detail = payload.detail.map((item) => item.msg || JSON.stringify(item)).join(', ')
      }
    } else {
      const text = await response.text()
      if (response.status >= 500 && /proxy|ECONNREFUSED|ECONNRESET|ENOTFOUND/i.test(text)) {
        return 'Backend is unavailable. Start the API on port 8000, then refresh.'
      }
    }
  } catch {
    // Keep the status fallback when the body cannot be read.
  }

  // Never surface raw stack traces or HTML error pages.
  if (/traceback|exception at|stack trace|<html/i.test(detail)) {
    detail = 'Something went wrong. Please try again.'
  }

  if (response.status === 401) {
    return 'Session expired. Please sign in again.'
  }
  if (response.status === 403) {
    return detail && !detail.startsWith('Request failed')
      ? detail
      : 'You do not have permission to perform this action.'
  }
  if (response.status === 413) {
    return detail && !detail.startsWith('Request failed')
      ? detail
      : 'The file or request is too large.'
  }
  if (response.status === 429) {
    return detail && !detail.startsWith('Request failed')
      ? detail
      : 'Too many requests. Please wait a moment and try again.'
  }
  if (response.status >= 500) {
    return 'A server error occurred. Please try again or contact an administrator.'
  }
  return detail
}

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = getStoredToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(apiV1Url(path), { ...options, headers })
  if (response.status === 401) {
    clearAuth()
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.assign('/login')
    }
    throw Object.assign(new Error('Session expired. Please sign in again.'), { status: 401 })
  }
  if (!response.ok) {
    throw Object.assign(new Error(await parseApiError(response)), { status: response.status })
  }
  if (response.status === 204) {
    return null
  }
  return response.json()
}
