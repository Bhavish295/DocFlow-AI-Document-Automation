import { apiRequest as request } from './apiClient'


export function listWorkflows() {
  return request('/workflows')
}

export function getWorkflow(workflowId) {
  return request(`/workflows/${workflowId}`)
}

export function triggerWorkflow(workflowId, payload) {
  return request(`/workflows/${workflowId}/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listWorkflowExecutions(workflowId, { page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return request(`/workflows/${workflowId}/executions?${params.toString()}`)
}

export function getWorkflowExecution(executionId) {
  return request(`/workflow-executions/${executionId}`)
}

