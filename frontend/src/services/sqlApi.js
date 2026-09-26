import { apiRequest as request } from './apiClient'


export function askBusinessDataQuestion(payload) {
  return request('/sql/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function validateSql(payload) {
  return request('/sql/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

