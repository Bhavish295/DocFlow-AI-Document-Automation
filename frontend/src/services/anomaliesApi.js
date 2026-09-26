import { apiRequest as request } from './apiClient'


export function getAnomalySummary() {
  return request('/anomalies/summary')
}

export function trainAnomalyModel(payload = {}) {
  return request('/anomalies/train', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function scoreAnomalies(payload) {
  return request('/anomalies/score', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listAnomalies({
  page = 1,
  pageSize = 20,
  status,
  minScore,
  vendor,
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
  if (minScore !== undefined && minScore !== null && minScore !== '') {
    params.set('min_score', String(minScore))
  }
  if (vendor) params.set('vendor', vendor)
  return request(`/anomalies?${params.toString()}`)
}

export function listAnomalyModelRuns({ page = 1, pageSize = 10 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return request(`/anomaly-model-runs?${params.toString()}`)
}

export function getDocumentAnomaly(documentId) {
  return request(`/anomalies/${documentId}`)
}

