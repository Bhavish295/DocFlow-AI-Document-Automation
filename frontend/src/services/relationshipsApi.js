import { apiRequest as request } from './apiClient'

export function listDocumentRelationships(documentId) {
  if (documentId) {
    return request(`/document-relationships/${documentId}`)
  }
  return request('/document-relationships')
}

export function suggestDocumentRelationships(documentId) {
  return request(`/document-relationships/suggestions/${documentId}`)
}

export function createDocumentRelationship(payload) {
  return request('/document-relationships', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteDocumentRelationship(relationshipId) {
  return request(`/document-relationships/${relationshipId}`, {
    method: 'DELETE',
  })
}
