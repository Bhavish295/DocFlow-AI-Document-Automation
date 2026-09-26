import { apiRequest as request } from './apiClient'


export function listReviews({
  page = 1,
  pageSize = 20,
  status,
  priority,
  reason,
  sortBy = 'created_at',
  sortOrder = 'desc',
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort_by: sortBy,
    sort_order: sortOrder,
  })
  if (status) params.set('status', status)
  if (priority) params.set('priority', priority)
  if (reason) params.set('reason', reason)
  return request(`/reviews?${params.toString()}`)
}

export function getReview(reviewId) {
  return request(`/reviews/${reviewId}`)
}

export function updateReview(reviewId, data) {
  return request(`/reviews/${reviewId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function startReview(reviewId, data = {}) {
  return request(`/reviews/${reviewId}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function approveReview(reviewId, data = {}) {
  return request(`/reviews/${reviewId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function rejectReview(reviewId, data = {}) {
  return request(`/reviews/${reviewId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

