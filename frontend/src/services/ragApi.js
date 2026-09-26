import { apiRequest as request } from './apiClient'


export function askQuestion(payload) {
  return request('/rag/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function searchKnowledge(payload) {
  return request('/rag/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function indexDocument(documentId) {
  return request(`/documents/${documentId}/index`, { method: 'POST' })
}

export function getDocumentIndexStatus(documentId) {
  return request(`/documents/${documentId}/index-status`)
}

