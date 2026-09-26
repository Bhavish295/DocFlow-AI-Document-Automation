import { apiV1Url } from '../config'

const TOKEN_KEY = 'docflow_access_token'
const USER_KEY = 'docflow_auth_user'

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function storeAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export async function loginRequest(username, password) {
  const response = await fetch(apiV1Url('/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail =
      typeof payload.detail === 'string' ? payload.detail : 'Login failed.'
    throw Object.assign(new Error(detail), { status: response.status })
  }
  return payload
}

export async function fetchCurrentUser(token) {
  const response = await fetch(apiV1Url('/auth/me'), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw Object.assign(new Error('Session expired.'), { status: response.status })
  }
  return response.json()
}

export function listUsersRequest({ page = 1, pageSize = 50 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return fetch(apiV1Url(`/users?${params}`), {
    headers: {
      Authorization: `Bearer ${getStoredToken()}`,
    },
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw Object.assign(
        new Error(typeof payload.detail === 'string' ? payload.detail : 'Failed to load users.'),
        { status: response.status },
      )
    }
    return payload
  })
}

export function createUserRequest(body) {
  return fetch(apiV1Url('/users'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getStoredToken()}`,
    },
    body: JSON.stringify(body),
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw Object.assign(
        new Error(typeof payload.detail === 'string' ? payload.detail : 'Failed to create user.'),
        { status: response.status },
      )
    }
    return payload
  })
}

export function deactivateUserRequest(userId) {
  return fetch(apiV1Url(`/users/${userId}`), {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${getStoredToken()}`,
    },
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw Object.assign(
        new Error(
          typeof payload.detail === 'string' ? payload.detail : 'Failed to deactivate user.',
        ),
        { status: response.status },
      )
    }
    return payload
  })
}
