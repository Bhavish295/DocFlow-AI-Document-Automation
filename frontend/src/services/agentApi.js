import { apiRequest as request } from './apiClient'

export function askAgent({ question, conversationId, maxSteps } = {}) {
  return request('/agent/ask', {
    method: 'POST',
    body: JSON.stringify({
      question,
      conversation_id: conversationId || undefined,
      max_steps: maxSteps || undefined,
    }),
  })
}

export function listAgentRuns({ conversationId, page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (conversationId) params.set('conversation_id', conversationId)
  return request(`/agent/runs?${params.toString()}`)
}
