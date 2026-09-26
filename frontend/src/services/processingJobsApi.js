import { apiRequest as request } from './apiClient'

export function getProcessingJob(jobId) {
  return request(`/processing-jobs/${jobId}`)
}

export function retryProcessingJob(jobId) {
  return request(`/processing-jobs/${jobId}/retry`, { method: 'POST' })
}

export function cancelProcessingJob(jobId) {
  return request(`/processing-jobs/${jobId}/cancel`, { method: 'POST' })
}

export function listDocumentProcessingJobs(documentId, { page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return request(`/documents/${documentId}/processing-jobs?${params.toString()}`)
}

const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed', 'cancelled'])

export function isTerminalJobStatus(status) {
  return TERMINAL_JOB_STATUSES.has(status)
}

export async function waitForProcessingJob(jobId, { onUpdate, intervalMs = 500, maxAttempts = 120 } = {}) {
  let last = null
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    last = await getProcessingJob(jobId)
    onUpdate?.(last)
    if (isTerminalJobStatus(last.status)) {
      return last
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return last
}
