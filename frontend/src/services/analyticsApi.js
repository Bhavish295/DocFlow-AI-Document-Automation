import { apiRequest as request } from './apiClient'

function buildParams(filters = {}) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  })
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function getAnalyticsSummary(filters = {}) {
  return request(`/analytics/summary${buildParams(filters)}`)
}

export function getDocumentAnalytics(filters = {}) {
  return request(`/analytics/documents${buildParams(filters)}`)
}

export function getInvoiceAnalytics(filters = {}) {
  return request(`/analytics/invoices${buildParams(filters)}`)
}

export function getVendorAnalytics(filters = {}) {
  return request(`/analytics/vendors${buildParams(filters)}`)
}

export function getReviewAnalytics() {
  return request('/analytics/reviews')
}

export function getValidationAnalytics() {
  return request('/analytics/validations')
}

export function getAnomalyAnalytics() {
  return request('/analytics/anomalies')
}

export function getDuplicateAnalytics() {
  return request('/analytics/duplicates')
}

export function getProcessingAnalytics() {
  return request('/analytics/processing')
}

export function getTrendsAnalytics(filters = {}) {
  return request(`/analytics/trends${buildParams(filters)}`)
}
