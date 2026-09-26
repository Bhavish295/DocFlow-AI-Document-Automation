import { apiRequest as request } from './apiClient'


export function listValidations({ page = 1, pageSize = 50 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return request(`/validations?${params.toString()}`)
}

export function getValidation(validationId) {
  return request(`/validations/${validationId}`)
}

export function createValidation(invoiceId, purchaseOrderId) {
  return request(`/validations/invoice/${invoiceId}/purchase-order/${purchaseOrderId}`, {
    method: 'POST',
  })
}

export function runThreeWayMatch(payload) {
  return request('/validations/three-way', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listThreeWayMatches({ page = 1, pageSize = 50 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return request(`/validations/three-way?${params.toString()}`)
}

export function getThreeWayMatch(matchId) {
  return request(`/validations/three-way/${matchId}`)
}

