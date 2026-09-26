import { apiRequest as request } from './apiClient'

export function listAuditLogs({
  page = 1,
  pageSize = 20,
  action,
  resourceType,
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (action && action.trim()) params.set('action', action.trim())
  if (resourceType && resourceType.trim()) params.set('resource_type', resourceType.trim())
  return request(`/audit-logs?${params.toString()}`)
}
