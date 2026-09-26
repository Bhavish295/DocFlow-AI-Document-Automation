import { apiV1Url } from '../config'
import { apiRequest as request } from './apiClient'

export function listDocuments({
  page = 1,
  pageSize = 20,
  search,
  documentType,
  status,
  uploadedFrom,
  uploadedTo,
  sortBy = 'uploaded_at',
  sortOrder = 'desc',
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort_by: sortBy,
    sort_order: sortOrder,
  })

  if (search && search.trim()) params.set('search', search.trim())
  if (documentType) params.set('document_type', documentType)
  if (status) params.set('status', status)
  if (uploadedFrom) params.set('uploaded_from', uploadedFrom)
  if (uploadedTo) params.set('uploaded_to', uploadedTo)

  return request(`/documents?${params.toString()}`)
}

export function getDocument(documentId) {
  return request(`/documents/${documentId}`)
}

export function uploadDocument(file, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append('file', file)

    xhr.open('POST', apiV1Url('/documents'))
    const token = localStorage.getItem('docflow_access_token')
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) {
        return
      }
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
          : xhr.status >= 500
            ? 'Backend request failed. Confirm the API is running on http://127.0.0.1:8000 and refresh.'
            : `Upload failed with status ${xhr.status}`
      reject(new Error(detail))
    }

    xhr.onerror = () => {
      reject(new Error('Network error while uploading the document.'))
    }

    xhr.send(formData)
  })
}

export function deleteDocument(documentId) {
  return request(`/documents/${documentId}`, { method: 'DELETE' })
}

export function processDocument(documentId) {
  return request(`/documents/${documentId}/process`, { method: 'POST' })
}

export function getDocumentText(documentId) {
  return request(`/documents/${documentId}/text`)
}

export function classifyDocument(documentId) {
  return request(`/documents/${documentId}/classify`, { method: 'POST' })
}

export function getDocumentClassification(documentId) {
  return request(`/documents/${documentId}/classification`)
}

export function extractInvoice(documentId) {
  return request(`/documents/${documentId}/extract`, { method: 'POST' })
}

export function getDocumentInvoice(documentId) {
  return request(`/documents/${documentId}/invoice`)
}

export function extractPurchaseOrder(documentId) {
  return request(`/documents/${documentId}/extract-po`, { method: 'POST' })
}

export function getDocumentPurchaseOrder(documentId) {
  return request(`/documents/${documentId}/purchase-order`)
}

export function extractGoodsReceipt(documentId) {
  return request(`/documents/${documentId}/extract-grn`, { method: 'POST' })
}

export function getDocumentGoodsReceipt(documentId) {
  return request(`/documents/${documentId}/goods-receipt`)
}

export function getDocumentLineItems(documentId) {
  return request(`/documents/${documentId}/line-items`)
}

export function extractDocumentLineItems(documentId) {
  return request(`/documents/${documentId}/extract-line-items`, { method: 'POST' })
}

export function indexDocument(documentId) {
  return request(`/documents/${documentId}/index`, { method: 'POST' })
}

export function getDocumentIndexStatus(documentId) {
  return request(`/documents/${documentId}/index-status`)
}
