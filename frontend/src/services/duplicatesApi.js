import { apiRequest as request } from './apiClient'


export function checkDuplicates(documentId) {
  return request(`/duplicates/check/${documentId}`, { method: 'POST' })
}

export function listDuplicates({
  status,
  detectionType,
  page = 1,
  pageSize = 20,
  sortBy = 'detected_at',
  sortOrder = 'desc',
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort_by: sortBy,
    sort_order: sortOrder,
  })
  if (status) params.set('status', status)
  if (detectionType) params.set('detection_type', detectionType)
  return request(`/duplicates?${params.toString()}`)
}

export function getDocumentDuplicates(documentId) {
  return request(`/duplicates/${documentId}`)
}

export function resolveDuplicate(duplicateId, status) {
  return request(`/duplicates/${duplicateId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export function getDuplicatesSummary() {
  return request('/duplicates/summary')
}

