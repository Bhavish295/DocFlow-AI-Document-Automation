import { apiRequest } from './apiClient'

export function getFieldIntelligence(documentId) {
  return apiRequest(`/documents/${documentId}/field-intelligence`)
}
