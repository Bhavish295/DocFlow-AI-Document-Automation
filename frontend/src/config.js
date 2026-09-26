/**
 * API base URL for browser requests.
 *
 * Empty / unset => same-origin relative paths (Vite proxy in dev, nginx in Docker).
 * Set VITE_API_BASE_URL to an absolute origin only when the API is on another host.
 */
export function getApiBaseUrl() {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null) {
    return ''
  }
  const trimmed = String(raw).trim()
  if (!trimmed || trimmed === '/') {
    return ''
  }
  return trimmed.replace(/\/$/, '')
}

/** Build a full path under /api/v1 (path should start with /). */
export function apiV1Url(path) {
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${getApiBaseUrl()}/api/v1${suffix}`
}
