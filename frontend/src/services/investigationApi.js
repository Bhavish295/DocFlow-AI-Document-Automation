import { apiRequest as request } from './apiClient'


export function askInvestigation(payload) {
  return request('/investigations/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

