import { apiV1Url } from '../config'
import { apiRequest as request } from './apiClient'
import { getStoredToken } from './authApi'

export function listIngestions({
  page = 1,
  pageSize = 20,
  sourceType,
  status,
  createdFrom,
  createdTo,
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (sourceType) params.set('source_type', sourceType)
  if (status) params.set('status', status)
  if (createdFrom) params.set('created_from', createdFrom)
  if (createdTo) params.set('created_to', createdTo)
  return request(`/ingestion?${params.toString()}`)
}

export function getIngestion(ingestionId) {
  return request(`/ingestion/${ingestionId}`)
}

export function ingestBatch(files, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }

    xhr.open('POST', apiV1Url('/ingestion/batch'))
    const token = getStoredToken()
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) return
      onProgress(Math.round((event.loaded / event.total) * 100))
    }

    xhr.onload = () => {
      let payload = null
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        reject(new Error('Invalid response from server.'))
        return
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload)
        return
      }
      const detail =
        typeof payload?.detail === 'string'
          ? payload.detail
          : `Batch upload failed with status ${xhr.status}`
      reject(Object.assign(new Error(detail), { status: xhr.status }))
    }

    xhr.onerror = () => {
      reject(new Error('Network error while uploading the batch.'))
    }

    xhr.send(formData)
  })
}

export function getEmailIngestionStatus() {
  return request('/ingestion/email/status')
}

export function pollEmailIngestion() {
  return request('/ingestion/email/poll', { method: 'POST' })
}
