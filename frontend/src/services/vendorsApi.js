import { apiRequest as request } from './apiClient'


export function getVendors({ page = 1, pageSize = 50 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return request(`/vendors?${params.toString()}`)
}

export function getVendor(vendorId) {
  return request(`/vendors/${vendorId}`)
}

export function createVendor(data) {
  return request('/vendors', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function updateVendor(vendorId, data) {
  return request(`/vendors/${vendorId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteVendor(vendorId) {
  return request(`/vendors/${vendorId}`, { method: 'DELETE' })
}

