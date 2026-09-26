import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Permission } from '../auth/permissions'
import ClassificationDetailsModal from '../components/documents/ClassificationDetailsModal'
import DocumentTextModal from '../components/documents/DocumentTextModal'
import DuplicateDetailsModal from '../components/documents/DuplicateDetailsModal'
import FieldIntelligenceModal from '../components/documents/FieldIntelligenceModal'
import InvoiceDataModal from '../components/documents/InvoiceDataModal'
import LineItemsModal from '../components/documents/LineItemsModal'
import ProcessingStatus from '../components/documents/ProcessingStatus'
import PurchaseOrderDataModal from '../components/documents/PurchaseOrderDataModal'
import RelationshipsModal from '../components/documents/RelationshipsModal'
import {
  classifyDocument,
  deleteDocument,
  extractGoodsReceipt,
  extractInvoice,
  extractPurchaseOrder,
  getDocument,
  getDocumentClassification,
  getDocumentInvoice,
  getDocumentLineItems,
  getDocumentPurchaseOrder,
  getDocumentText,
  indexDocument,
  listDocuments,
  processDocument,
  uploadDocument,
} from '../services/documentsApi'
import {
  isTerminalJobStatus,
  retryProcessingJob,
  waitForProcessingJob,
} from '../services/processingJobsApi'
import {
  checkDuplicates,
  getDocumentDuplicates,
  resolveDuplicate,
} from '../services/duplicatesApi'
import { getFieldIntelligence } from '../services/fieldIntelligenceApi'
import {
  createDocumentRelationship,
  deleteDocumentRelationship,
  listDocumentRelationships,
  suggestDocumentRelationships,
} from '../services/relationshipsApi'
import { ingestBatch } from '../services/ingestionApi'
import './Documents.css'

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.csv', '.png', '.jpg', '.jpeg']
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')
const PROCESSABLE_TYPES = new Set(['pdf', 'png', 'jpg', 'jpeg'])

const DOCUMENT_TYPE_LABELS = {
  invoice: 'Invoice',
  purchase_order: 'Purchase Order',
  goods_receipt: 'Goods Receipt',
  contract: 'Contract',
  receipt: 'Receipt',
  bank_statement: 'Bank Statement',
  other: 'Other',
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function statusLabel(status) {
  return status.replaceAll('_', ' ')
}

function documentTypeLabel(type) {
  if (!type) return '—'
  return DOCUMENT_TYPE_LABELS[type] || type
}

function formatConfidence(value) {
  if (value === null || value === undefined) return null
  return `${Math.round(Number(value) * 100)}%`
}

const SORT_OPTIONS = [
  { value: 'uploaded_at:desc', label: 'Newest first' },
  { value: 'uploaded_at:asc', label: 'Oldest first' },
  { value: 'filename:asc', label: 'Filename A–Z' },
  { value: 'filename:desc', label: 'Filename Z–A' },
  { value: 'document_type:asc', label: 'Type' },
  { value: 'status:asc', label: 'Status' },
]

const EMPTY_FILTERS = {
  search: '',
  documentType: '',
  status: '',
  uploadedFrom: '',
  uploadedTo: '',
  sort: 'uploaded_at:desc',
}

const PAGE_SIZE = 20

function canProcess(doc) {
  return PROCESSABLE_TYPES.has(doc.file_type) && doc.status !== 'processing'
}

function parseSort(value) {
  const [sortBy, sortOrder] = String(value || 'uploaded_at:desc').split(':')
  return { sortBy, sortOrder }
}

function hasActiveFilters(filters) {
  return Boolean(
    filters.search.trim()
      || filters.documentType
      || filters.status
      || filters.uploadedFrom
      || filters.uploadedTo
      || filters.sort !== EMPTY_FILTERS.sort,
  )
}

export default function Documents() {
  const { can } = useAuth()
  const canWrite = can(Permission.DOCUMENTS_WRITE)
  const canProcessDocs = can(Permission.DOCUMENTS_PROCESS)
  const canExtract = can(Permission.DOCUMENTS_EXTRACT)
  const canIndex = can(Permission.DOCUMENTS_INDEX)
  const canCheckDuplicates = can(Permission.DUPLICATES_CHECK)
  const canResolveDuplicates = can(Permission.DUPLICATES_RESOLVE)
  const canManageRelationships = can(Permission.RELATIONSHIPS_WRITE)
  const inputRef = useRef(null)
  const batchInputRef = useRef(null)
  const [documents, setDocuments] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrevious, setHasPrevious] = useState(false)
  const [page, setPage] = useState(1)
  const [draftFilters, setDraftFilters] = useState(EMPTY_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [batchResults, setBatchResults] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [deletingId, setDeletingId] = useState(null)
  const [processingId, setProcessingId] = useState(null)
  const [processingJobs, setProcessingJobs] = useState({})
  const [retryingJobId, setRetryingJobId] = useState(null)
  const [classifyingId, setClassifyingId] = useState(null)
  const [extractingId, setExtractingId] = useState(null)
  const [indexingId, setIndexingId] = useState(null)
  const [viewerOpen, setViewerOpen] = useState(false)
  const [viewerLoading, setViewerLoading] = useState(false)
  const [viewerError, setViewerError] = useState('')
  const [viewerDoc, setViewerDoc] = useState(null)
  const [viewerText, setViewerText] = useState('')
  const [invoiceOpen, setInvoiceOpen] = useState(false)
  const [invoiceLoading, setInvoiceLoading] = useState(false)
  const [invoiceError, setInvoiceError] = useState('')
  const [invoiceDoc, setInvoiceDoc] = useState(null)
  const [invoiceData, setInvoiceData] = useState(null)
  const [poOpen, setPoOpen] = useState(false)
  const [poLoading, setPoLoading] = useState(false)
  const [poError, setPoError] = useState('')
  const [poDoc, setPoDoc] = useState(null)
  const [poData, setPoData] = useState(null)
  const [duplicateOpen, setDuplicateOpen] = useState(false)
  const [duplicateLoading, setDuplicateLoading] = useState(false)
  const [duplicateError, setDuplicateError] = useState('')
  const [duplicateDoc, setDuplicateDoc] = useState(null)
  const [duplicateItems, setDuplicateItems] = useState([])
  const [checkingDuplicatesId, setCheckingDuplicatesId] = useState(null)
  const [resolvingDuplicateId, setResolvingDuplicateId] = useState(null)
  const [fieldIntelOpen, setFieldIntelOpen] = useState(false)
  const [fieldIntelLoading, setFieldIntelLoading] = useState(false)
  const [fieldIntelError, setFieldIntelError] = useState('')
  const [fieldIntelDoc, setFieldIntelDoc] = useState(null)
  const [fieldIntelReport, setFieldIntelReport] = useState(null)
  const [classificationOpen, setClassificationOpen] = useState(false)
  const [classificationLoading, setClassificationLoading] = useState(false)
  const [classificationError, setClassificationError] = useState('')
  const [classificationDoc, setClassificationDoc] = useState(null)
  const [classificationData, setClassificationData] = useState(null)
  const [relationshipsOpen, setRelationshipsOpen] = useState(false)
  const [relationshipsLoading, setRelationshipsLoading] = useState(false)
  const [relationshipsError, setRelationshipsError] = useState('')
  const [relationshipsDoc, setRelationshipsDoc] = useState(null)
  const [relationships, setRelationships] = useState([])
  const [relationshipSuggestions, setRelationshipSuggestions] = useState([])
  const [confirmingRelationshipKey, setConfirmingRelationshipKey] = useState(null)
  const [deletingRelationshipId, setDeletingRelationshipId] = useState(null)
  const [lineItemsOpen, setLineItemsOpen] = useState(false)
  const [lineItemsLoading, setLineItemsLoading] = useState(false)
  const [lineItemsError, setLineItemsError] = useState('')
  const [lineItemsDoc, setLineItemsDoc] = useState(null)
  const [lineItems, setLineItems] = useState([])

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { sortBy, sortOrder } = parseSort(appliedFilters.sort)
      const data = await listDocuments({
        page,
        pageSize: PAGE_SIZE,
        search: appliedFilters.search,
        documentType: appliedFilters.documentType || undefined,
        status: appliedFilters.status || undefined,
        uploadedFrom: appliedFilters.uploadedFrom || undefined,
        uploadedTo: appliedFilters.uploadedTo || undefined,
        sortBy,
        sortOrder,
      })
      setDocuments(data.items)
      setTotal(data.total)
      setTotalPages(data.total_pages || 0)
      setHasNext(Boolean(data.has_next))
      setHasPrevious(Boolean(data.has_previous))
    } catch (err) {
      setError(err.message || 'Failed to load documents.')
    } finally {
      setLoading(false)
    }
  }, [appliedFilters, page])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  const applyFilters = (event) => {
    event?.preventDefault?.()
    setPage(1)
    setAppliedFilters({ ...draftFilters })
  }

  const clearFilters = () => {
    setDraftFilters(EMPTY_FILTERS)
    setAppliedFilters(EMPTY_FILTERS)
    setPage(1)
  }

  const onSortChange = (value) => {
    const next = { ...draftFilters, sort: value }
    setDraftFilters(next)
    setAppliedFilters(next)
    setPage(1)
  }

  const updateDraft = (field) => (event) => {
    setDraftFilters((current) => ({ ...current, [field]: event.target.value }))
  }

  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const rangeEnd = Math.min(page * PAGE_SIZE, total)
  const filtersActive = hasActiveFilters(appliedFilters)

  const handleUpload = async (file) => {
    if (!file || uploading) return

    setUploading(true)
    setProgress(0)
    setError('')
    setSuccess('')
    setBatchResults(null)

    try {
      const created = await uploadDocument(file, { onProgress: setProgress })
      setSuccess(`Uploaded “${created.original_filename}” successfully.`)
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Upload failed.')
    } finally {
      setUploading(false)
      setProgress(0)
      if (inputRef.current) {
        inputRef.current.value = ''
      }
    }
  }

  const handleBatchUpload = async (fileList) => {
    const files = Array.from(fileList || []).filter(Boolean)
    if (files.length === 0 || uploading) return
    if (files.length === 1) {
      await handleUpload(files[0])
      return
    }

    setUploading(true)
    setProgress(0)
    setError('')
    setSuccess('')
    setBatchResults(null)

    try {
      const result = await ingestBatch(files, { onProgress: setProgress })
      setBatchResults(result)
      const parts = [
        `${result.accepted} accepted`,
        result.failed ? `${result.failed} failed` : null,
        result.skipped ? `${result.skipped} skipped` : null,
      ].filter(Boolean)
      setSuccess(`Batch upload finished: ${parts.join(', ')}.`)
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Batch upload failed.')
    } finally {
      setUploading(false)
      setProgress(0)
      if (batchInputRef.current) {
        batchInputRef.current.value = ''
      }
    }
  }

  const onFileInputChange = (event) => {
    const file = event.target.files?.[0]
    if (file) {
      handleUpload(file)
    }
  }

  const onBatchInputChange = (event) => {
    const files = event.target.files
    if (files?.length) {
      handleBatchUpload(files)
    }
  }

  const onDrop = (event) => {
    event.preventDefault()
    setDragging(false)
    const files = event.dataTransfer.files
    if (!files?.length) return
    if (files.length === 1) {
      handleUpload(files[0])
      return
    }
    handleBatchUpload(files)
  }

  const onDelete = async (document) => {
    const confirmed = window.confirm(
      `Delete “${document.original_filename}”? This cannot be undone.`,
    )
    if (!confirmed) return

    setDeletingId(document.id)
    setError('')
    setSuccess('')
    try {
      await deleteDocument(document.id)
      setSuccess(`Deleted “${document.original_filename}”.`)
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Failed to delete document.')
    } finally {
      setDeletingId(null)
    }
  }

  const onProcess = async (document) => {
    setProcessingId(document.id)
    setError('')
    setSuccess('')
    try {
      const result = await processDocument(document.id)
      let job = {
        id: result.job_id,
        document_id: document.id,
        status: result.job_status || 'queued',
        progress: result.progress ?? 0,
        current_stage: result.current_stage || 'queued',
        error_message: result.processing_error || null,
      }
      setProcessingJobs((prev) => ({ ...prev, [document.id]: job }))

      if (result.job_id && !isTerminalJobStatus(job.status)) {
        job = await waitForProcessingJob(result.job_id, {
          onUpdate: (next) => {
            setProcessingJobs((prev) => ({ ...prev, [document.id]: next }))
          },
        })
      }

      const refreshed = result.job_id ? await getDocument(document.id) : result
      setDocuments((prev) => prev.map((item) => (item.id === document.id ? refreshed : item)))

      if (job?.status === 'completed' || refreshed.status === 'processed') {
        const typeLabel = documentTypeLabel(refreshed.document_type)
        setSuccess(`Processed “${refreshed.original_filename}” as ${typeLabel}.`)
      } else if (job?.status === 'failed' || refreshed.status === 'failed') {
        setError(
          job?.error_message
            || refreshed.processing_error
            || `Processing failed for “${refreshed.original_filename}”.`,
        )
      }
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Processing failed.')
      await loadDocuments()
    } finally {
      setProcessingId(null)
    }
  }

  const onRetryProcessing = async (document) => {
    const existing = processingJobs[document.id]
    if (!existing?.id) return
    setRetryingJobId(existing.id)
    setProcessingId(document.id)
    setError('')
    setSuccess('')
    try {
      const started = await retryProcessingJob(existing.id)
      setProcessingJobs((prev) => ({ ...prev, [document.id]: started }))
      let job = started
      if (!isTerminalJobStatus(started.status)) {
        job = await waitForProcessingJob(started.id, {
          onUpdate: (next) => {
            setProcessingJobs((prev) => ({ ...prev, [document.id]: next }))
          },
        })
      }
      const refreshed = await getDocument(document.id)
      setDocuments((prev) => prev.map((item) => (item.id === document.id ? refreshed : item)))
      if (job?.status === 'completed') {
        setSuccess(`Retry completed for “${refreshed.original_filename}”.`)
      } else if (job?.status === 'failed') {
        setError(job.error_message || 'Retry failed.')
      }
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Retry failed.')
    } finally {
      setRetryingJobId(null)
      setProcessingId(null)
    }
  }

  const onClassify = async (document) => {
    setClassifyingId(document.id)
    setError('')
    setSuccess('')
    try {
      const result = await classifyDocument(document.id)
      const typeLabel = documentTypeLabel(result.document_type)
      const confidence = formatConfidence(result.classification_confidence)
      setSuccess(
        confidence
          ? `Classified “${result.original_filename}” as ${typeLabel} (${confidence}).`
          : `Classified “${result.original_filename}” as ${typeLabel}.`,
      )
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Classification failed.')
    } finally {
      setClassifyingId(null)
    }
  }

  const onExtract = async (document) => {
    setExtractingId(document.id)
    setError('')
    setSuccess('')
    try {
      if (document.document_type === 'purchase_order') {
        const purchaseOrder = await extractPurchaseOrder(document.id)
        setSuccess(
          `Extracted PO data for “${document.original_filename}”`
          + (purchaseOrder.po_number ? ` (${purchaseOrder.po_number}).` : '.'),
        )
      } else if (document.document_type === 'goods_receipt') {
        const goodsReceipt = await extractGoodsReceipt(document.id)
        setSuccess(
          `Extracted GRN data for “${document.original_filename}”`
          + (goodsReceipt.grn_number ? ` (${goodsReceipt.grn_number}).` : '.'),
        )
      } else {
        const invoice = await extractInvoice(document.id)
        setSuccess(
          `Extracted invoice data for “${document.original_filename}”`
          + (invoice.invoice_number ? ` (${invoice.invoice_number}).` : '.'),
        )
      }
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Extraction failed.')
    } finally {
      setExtractingId(null)
    }
  }

  const loadRelationshipsForDoc = async (document) => {
    const [linked, suggested] = await Promise.all([
      listDocumentRelationships(document.id),
      suggestDocumentRelationships(document.id),
    ])
    setRelationships(linked.items || [])
    setRelationshipSuggestions(suggested.items || [])
  }

  const onViewRelationships = async (document) => {
    setRelationshipsDoc(document)
    setRelationshipsOpen(true)
    setRelationshipsLoading(true)
    setRelationshipsError('')
    setRelationships([])
    setRelationshipSuggestions([])
    try {
      await loadRelationshipsForDoc(document)
    } catch (err) {
      setRelationshipsError(err.message || 'Failed to load relationships.')
    } finally {
      setRelationshipsLoading(false)
    }
  }

  const onConfirmRelationshipSuggestion = async (suggestion) => {
    const key = `${suggestion.relationship_type}:${suggestion.source_document_id}:${suggestion.target_document_id}`
    setConfirmingRelationshipKey(key)
    setRelationshipsError('')
    try {
      await createDocumentRelationship({
        source_document_id: suggestion.source_document_id,
        target_document_id: suggestion.target_document_id,
        relationship_type: suggestion.relationship_type,
        match_key: suggestion.match_key,
      })
      if (relationshipsDoc) {
        await loadRelationshipsForDoc(relationshipsDoc)
      }
      setSuccess('Relationship confirmed.')
    } catch (err) {
      setRelationshipsError(err.message || 'Could not confirm relationship.')
    } finally {
      setConfirmingRelationshipKey(null)
    }
  }

  const onDeleteRelationship = async (item) => {
    setDeletingRelationshipId(item.id)
    setRelationshipsError('')
    try {
      await deleteDocumentRelationship(item.id)
      if (relationshipsDoc) {
        await loadRelationshipsForDoc(relationshipsDoc)
      }
    } catch (err) {
      setRelationshipsError(err.message || 'Could not remove relationship.')
    } finally {
      setDeletingRelationshipId(null)
    }
  }

  const onViewLineItems = async (document) => {
    setLineItemsDoc(document)
    setLineItemsOpen(true)
    setLineItemsLoading(true)
    setLineItemsError('')
    setLineItems([])
    try {
      const payload = await getDocumentLineItems(document.id)
      setLineItems(payload.items || [])
    } catch (err) {
      setLineItemsError(err.message || 'Failed to load line items.')
    } finally {
      setLineItemsLoading(false)
    }
  }

  const onIndex = async (document) => {
    setIndexingId(document.id)
    setError('')
    setSuccess('')
    try {
      const result = await indexDocument(document.id)
      if (result.status === 'indexed') {
        setSuccess(`Indexed “${document.original_filename}” (${result.chunks_created} chunks).`)
      } else {
        setError(result.detail || `Indexing skipped for “${document.original_filename}”.`)
      }
      await loadDocuments()
    } catch (err) {
      setError(err.message || 'Indexing failed.')
      await loadDocuments()
    } finally {
      setIndexingId(null)
    }
  }

  const onViewInvoice = async (document) => {
    setInvoiceDoc(document)
    setInvoiceOpen(true)
    setInvoiceLoading(true)
    setInvoiceError('')
    setInvoiceData(null)
    try {
      const payload = await getDocumentInvoice(document.id)
      setInvoiceData(payload)
    } catch (err) {
      setInvoiceError(err.message || 'Failed to load invoice data.')
    } finally {
      setInvoiceLoading(false)
    }
  }

  const onViewClassification = async (document) => {
    setClassificationDoc(document)
    setClassificationOpen(true)
    setClassificationLoading(true)
    setClassificationError('')
    setClassificationData(null)
    try {
      const payload = await getDocumentClassification(document.id)
      setClassificationData(payload)
    } catch (err) {
      setClassificationError(err.message || 'Failed to load classification.')
    } finally {
      setClassificationLoading(false)
    }
  }

  const onViewFieldIntelligence = async (document) => {
    setFieldIntelDoc(document)
    setFieldIntelOpen(true)
    setFieldIntelLoading(true)
    setFieldIntelError('')
    setFieldIntelReport(null)
    try {
      const payload = await getFieldIntelligence(document.id)
      setFieldIntelReport(payload)
    } catch (err) {
      setFieldIntelError(err.message || 'Failed to load field intelligence.')
    } finally {
      setFieldIntelLoading(false)
    }
  }

  const onViewPurchaseOrder = async (document) => {
    setPoDoc(document)
    setPoOpen(true)
    setPoLoading(true)
    setPoError('')
    setPoData(null)
    try {
      const payload = await getDocumentPurchaseOrder(document.id)
      setPoData(payload)
    } catch (err) {
      setPoError(err.message || 'Failed to load purchase order data.')
    } finally {
      setPoLoading(false)
    }
  }

  const onViewText = async (document) => {
    setViewerDoc(document)
    setViewerOpen(true)
    setViewerLoading(true)
    setViewerError('')
    setViewerText('')
    try {
      const payload = await getDocumentText(document.id)
      setViewerDoc({
        ...document,
        status: payload.status,
        processing_error: payload.processing_error,
      })
      setViewerText(payload.extracted_text || '')
      if (payload.status === 'failed' && payload.processing_error) {
        setViewerError(payload.processing_error)
      }
    } catch (err) {
      setViewerError(err.message || 'Failed to load extracted text.')
    } finally {
      setViewerLoading(false)
    }
  }

  const onCheckDuplicates = async (document) => {
    setCheckingDuplicatesId(document.id)
    setDuplicateDoc(document)
    setDuplicateOpen(true)
    setDuplicateLoading(true)
    setDuplicateError('')
    setDuplicateItems([])
    setError('')
    setSuccess('')
    try {
      const payload = await checkDuplicates(document.id)
      setDuplicateItems(payload.items || [])
      const count = payload.items?.length || 0
      setSuccess(
        count > 0
          ? `Found ${count} duplicate candidate${count === 1 ? '' : 's'} for “${document.original_filename}”.`
          : `No duplicate candidates for “${document.original_filename}”.`,
      )
      await loadDocuments()
    } catch (err) {
      setDuplicateError(err.message || 'Duplicate check failed.')
      setError(err.message || 'Duplicate check failed.')
    } finally {
      setDuplicateLoading(false)
      setCheckingDuplicatesId(null)
    }
  }

  const onViewDuplicates = async (document) => {
    setDuplicateDoc(document)
    setDuplicateOpen(true)
    setDuplicateLoading(true)
    setDuplicateError('')
    setDuplicateItems([])
    try {
      const payload = await getDocumentDuplicates(document.id)
      setDuplicateItems(payload.items || [])
    } catch (err) {
      setDuplicateError(err.message || 'Failed to load duplicates.')
    } finally {
      setDuplicateLoading(false)
    }
  }

  const onResolveDuplicate = async (item, status) => {
    setResolvingDuplicateId(item.id)
    setDuplicateError('')
    try {
      await resolveDuplicate(item.id, status)
      if (duplicateDoc?.id) {
        const payload = await getDocumentDuplicates(duplicateDoc.id)
        setDuplicateItems(payload.items || [])
      }
      await loadDocuments()
    } catch (err) {
      setDuplicateError(err.message || 'Failed to update duplicate status.')
    } finally {
      setResolvingDuplicateId(null)
    }
  }

  const renderDocumentType = (doc) => {
    if (!doc.document_type) {
      return <span className="documents__doc-type documents__doc-type--empty">—</span>
    }

    const confidence = formatConfidence(doc.classification_confidence)
    return (
      <span className={`documents__doc-type documents__doc-type--${doc.document_type}`}>
        <span className="documents__doc-type-label">{documentTypeLabel(doc.document_type)}</span>
        {confidence && <span className="documents__doc-type-confidence">{confidence}</span>}
      </span>
    )
  }

  const busy = (doc) =>
    processingId === doc.id ||
    classifyingId === doc.id ||
    extractingId === doc.id ||
    indexingId === doc.id ||
    checkingDuplicatesId === doc.id ||
    deletingId === doc.id

  const renderActions = (doc) => (
    <div className="documents__actions">
      {canProcessDocs && canProcess(doc) && (
        <button
          type="button"
          className="documents__action"
          onClick={() => onProcess(doc)}
          disabled={busy(doc)}
        >
          {processingId === doc.id || doc.status === 'processing' ? 'Processing…' : 'Process'}
        </button>
      )}
      {canProcessDocs && doc.status === 'processed' && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onClassify(doc)}
          disabled={busy(doc)}
        >
          {classifyingId === doc.id ? 'Classifying…' : 'Classify'}
        </button>
      )}
      {doc.status === 'processed' && doc.document_type && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewClassification(doc)}
          disabled={busy(doc)}
        >
          View Classification
        </button>
      )}
      {canExtract && doc.document_type === 'invoice' && doc.status === 'processed' && (
        <button
          type="button"
          className="documents__action"
          onClick={() => onExtract(doc)}
          disabled={busy(doc)}
        >
          {extractingId === doc.id ? 'Extracting…' : 'Extract Data'}
        </button>
      )}
      {canExtract && doc.document_type === 'purchase_order' && doc.status === 'processed' && (
        <button
          type="button"
          className="documents__action"
          onClick={() => onExtract(doc)}
          disabled={busy(doc)}
        >
          {extractingId === doc.id ? 'Extracting…' : 'Extract PO Data'}
        </button>
      )}
      {canExtract && doc.document_type === 'goods_receipt' && doc.status === 'processed' && (
        <button
          type="button"
          className="documents__action"
          onClick={() => onExtract(doc)}
          disabled={busy(doc)}
        >
          {extractingId === doc.id ? 'Extracting…' : 'Extract GRN Data'}
        </button>
      )}
      {(doc.document_type === 'invoice' ||
        doc.document_type === 'purchase_order' ||
        doc.document_type === 'goods_receipt') &&
        doc.status === 'processed' && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewLineItems(doc)}
          disabled={busy(doc)}
        >
          Line Items
        </button>
      )}
      {doc.status === 'processed' && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewRelationships(doc)}
          disabled={busy(doc)}
        >
          Relationships
        </button>
      )}
      {doc.status === 'processed' &&
        (doc.document_type === 'invoice' ||
          doc.document_type === 'purchase_order' ||
          doc.document_type === 'goods_receipt') && (
        <a className="documents__action documents__action--secondary" href="/validation">
          3-Way Match
        </a>
      )}
      {canIndex && doc.status === 'processed' && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onIndex(doc)}
          disabled={busy(doc)}
        >
          {indexingId === doc.id
            ? 'Indexing…'
            : doc.rag_index_status === 'indexed'
              ? 'Re-index'
              : 'Index'}
        </button>
      )}
      {canCheckDuplicates && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onCheckDuplicates(doc)}
          disabled={busy(doc)}
        >
          {checkingDuplicatesId === doc.id ? 'Checking…' : 'Check Duplicates'}
        </button>
      )}
      {doc.duplicate_count > 0 && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewDuplicates(doc)}
          disabled={busy(doc)}
        >
          View Duplicates
        </button>
      )}
      {doc.has_invoice && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewInvoice(doc)}
          disabled={busy(doc)}
        >
          View Data
        </button>
      )}
      {doc.has_purchase_order && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewPurchaseOrder(doc)}
          disabled={busy(doc)}
        >
          View PO Data
        </button>
      )}
      {(doc.document_type === 'invoice' ||
        doc.document_type === 'purchase_order' ||
        doc.document_type === 'goods_receipt') && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewFieldIntelligence(doc)}
          disabled={busy(doc)}
        >
          Field Intelligence
        </button>
      )}
      {(doc.status === 'processed' || doc.status === 'failed') && (
        <button
          type="button"
          className="documents__action documents__action--secondary"
          onClick={() => onViewText(doc)}
          disabled={busy(doc)}
        >
          View Text
        </button>
      )}
      {canWrite && (
      <button
        type="button"
        className="documents__danger"
        onClick={() => onDelete(doc)}
        disabled={busy(doc)}
      >
        {deletingId === doc.id ? 'Deleting…' : 'Delete'}
      </button>
      )}
    </div>
  )

  return (
    <div className="documents">
      <section className="documents__intro">
        <div>
          <p className="documents__kicker">Library</p>
          <h2 className="documents__title">Documents</h2>
          <p className="documents__desc">
            Upload files, extract text, classify documents, pull invoice/PO fields,
            and validate invoices against purchase orders.
          </p>
        </div>
        {canWrite ? (
          <div className="documents__intro-actions">
            <button
              type="button"
              className="documents__primary"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
            >
              Upload Document
            </button>
            <button
              type="button"
              className="documents__secondary"
              onClick={() => batchInputRef.current?.click()}
              disabled={uploading}
            >
              Batch Upload
            </button>
          </div>
        ) : null}
        <input
          ref={inputRef}
          type="file"
          className="documents__file-input"
          accept={ACCEPT_ATTR}
          onChange={onFileInputChange}
          disabled={!canWrite}
        />
        <input
          ref={batchInputRef}
          type="file"
          className="documents__file-input"
          accept={ACCEPT_ATTR}
          multiple
          onChange={onBatchInputChange}
          disabled={!canWrite}
        />
      </section>

      {canWrite ? (
      <section
        className={`documents__dropzone ${dragging ? 'is-dragging' : ''} ${uploading ? 'is-uploading' : ''}`}
        onDragEnter={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={(event) => {
          event.preventDefault()
          setDragging(false)
        }}
        onDrop={onDrop}
        aria-label="Document upload dropzone"
      >
        <p className="documents__drop-title">
          {uploading ? 'Uploading…' : 'Drag and drop one or more files here'}
        </p>
        <p className="documents__drop-copy">
          Single file uses Upload Document; multiple files use Batch Upload
        </p>
        <p className="documents__types">
          Upload: PDF, DOCX, XLSX, CSV, PNG, JPG, JPEG · Process: PDF and images
        </p>
        {uploading && (
          <div className="documents__progress" role="progressbar" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100">
            <div className="documents__progress-bar" style={{ width: `${Math.max(progress, 8)}%` }} />
            <span>{progress}%</span>
          </div>
        )}
      </section>
      ) : null}

      {error && <div className="documents__alert documents__alert--error">{error}</div>}
      {success && <div className="documents__alert documents__alert--success">{success}</div>}

      {batchResults?.items?.length > 0 && (
        <section className="documents__batch-results" aria-label="Batch upload results">
          <h3>Batch results</h3>
          <ul>
            {batchResults.items.map((item) => (
              <li key={`${item.filename}-${item.ingestion_id || item.status}`}>
                <strong>{item.filename}</strong>
                <span className={`documents__batch-status documents__batch-status--${item.status}`}>
                  {item.status}
                </span>
                {item.document_id && (
                  <span className="documents__batch-meta">doc {String(item.document_id).slice(0, 8)}</span>
                )}
                {item.processing_job_id && (
                  <span className="documents__batch-meta">job {String(item.processing_job_id).slice(0, 8)}</span>
                )}
                {item.error && <span className="documents__batch-error">{item.error}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="documents__filters" aria-label="Document filters">
        <form className="documents__filters-form" onSubmit={applyFilters}>
          <label>
            Search
            <input
              value={draftFilters.search}
              onChange={updateDraft('search')}
              placeholder="Search documents..."
            />
          </label>
          <label>
            Document type
            <select value={draftFilters.documentType} onChange={updateDraft('documentType')}>
              <option value="">All Types</option>
              <option value="invoice">Invoice</option>
              <option value="purchase_order">Purchase Order</option>
              <option value="goods_receipt">Goods Receipt</option>
              <option value="contract">Contract</option>
              <option value="receipt">Receipt</option>
              <option value="bank_statement">Bank Statement</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Status
            <select value={draftFilters.status} onChange={updateDraft('status')}>
              <option value="">All Statuses</option>
              <option value="uploaded">Uploaded</option>
              <option value="processing">Processing</option>
              <option value="processed">Processed</option>
              <option value="failed">Failed</option>
            </select>
          </label>
          <label>
            From
            <input
              type="date"
              value={draftFilters.uploadedFrom}
              onChange={updateDraft('uploadedFrom')}
            />
          </label>
          <label>
            To
            <input
              type="date"
              value={draftFilters.uploadedTo}
              onChange={updateDraft('uploadedTo')}
            />
          </label>
          <label>
            Sort
            <select value={draftFilters.sort} onChange={(event) => onSortChange(event.target.value)}>
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <div className="documents__filters-actions">
            <button type="submit" className="documents__primary">
              Apply
            </button>
            <button type="button" className="documents__filter-clear" onClick={clearFilters}>
              Clear Filters
            </button>
          </div>
        </form>
      </section>

      <section className="documents__list-panel" aria-label="Uploaded documents">
        <div className="documents__list-header">
          <h3>Uploaded files</h3>
          <p>
            {loading
              ? 'Loading…'
              : total === 0
                ? '0 documents'
                : `Showing ${rangeStart}–${rangeEnd} of ${total} document${total === 1 ? '' : 's'}`}
          </p>
        </div>

        {loading && (
          <div className="documents__state">Loading documents…</div>
        )}

        {!loading && documents.length === 0 && !filtersActive && (
          <div className="documents__state">
            No documents uploaded yet.
          </div>
        )}

        {!loading && documents.length === 0 && filtersActive && (
          <div className="documents__state">
            <p>No documents match your current filters.</p>
            <button type="button" className="documents__filter-clear" onClick={clearFilters}>
              Clear Filters
            </button>
          </div>
        )}

        {!loading && documents.length > 0 && (
          <>
            <div className="documents__table-wrap">
              <table className="documents__table">
                <thead>
                  <tr>
                    <th>File Name</th>
                    <th>Format</th>
                    <th>Type</th>
                    <th>Vendor</th>
                    <th>Size</th>
                    <th>Status</th>
                    <th>Uploaded</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id}>
                      <td data-label="File Name">
                        <span className="documents__filename">{doc.original_filename}</span>
                        {doc.requires_review && (
                          <span className="documents__review-flag">Review Required</span>
                        )}
                        {doc.duplicate_count > 0 && (
                          <button
                            type="button"
                            className="documents__duplicate-flag"
                            onClick={() => onViewDuplicates(doc)}
                          >
                            Possible Duplicate ({doc.duplicate_count})
                          </button>
                        )}
                        {doc.rag_index_status === 'indexed' && (
                          <span className="documents__index-flag documents__index-flag--ok">Indexed</span>
                        )}
                        {doc.rag_index_status === 'failed' && (
                          <span
                            className="documents__index-flag documents__index-flag--fail"
                            title={doc.rag_index_error || 'Indexing failed'}
                          >
                            Indexing Failed
                          </span>
                        )}
                        {doc.status === 'processed' && !doc.rag_index_status && (
                          <span className="documents__index-flag">Not Indexed</span>
                        )}
                        {doc.status === 'failed' && doc.processing_error && (
                          <span className="documents__error-hint">{doc.processing_error}</span>
                        )}
                      </td>
                      <td data-label="Format">
                        <span className="documents__type">{doc.file_type.toUpperCase()}</span>
                      </td>
                      <td data-label="Type">{renderDocumentType(doc)}</td>
                      <td data-label="Vendor">
                        {(doc.has_invoice || doc.has_purchase_order || doc.has_goods_receipt) && doc.vendor_name
                          ? doc.vendor_name
                          : '—'}
                      </td>
                      <td data-label="Size">{formatBytes(doc.file_size)}</td>
                      <td data-label="Status">
                        <span className={`documents__status documents__status--${doc.status}`}>
                          {statusLabel(doc.status)}
                        </span>
                      </td>
                      <td data-label="Uploaded">{formatDate(doc.uploaded_at)}</td>
                      <td data-label="Actions">
                        {renderActions(doc)}
                        <ProcessingStatus
                          job={processingJobs[doc.id]}
                          onRetry={
                            processingJobs[doc.id]?.status === 'failed'
                              ? () => onRetryProcessing(doc)
                              : undefined
                          }
                          retrying={retryingJobId === processingJobs[doc.id]?.id}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="documents__cards">
              {documents.map((doc) => (
                <li key={doc.id} className="documents__card">
                  <div className="documents__card-top">
                    <p className="documents__filename">{doc.original_filename}</p>
                    <span className={`documents__status documents__status--${doc.status}`}>
                      {statusLabel(doc.status)}
                    </span>
                  </div>
                  {doc.requires_review && (
                    <p className="documents__review-flag">Review Required</p>
                  )}
                  {doc.duplicate_count > 0 && (
                    <button
                      type="button"
                      className="documents__duplicate-flag"
                      onClick={() => onViewDuplicates(doc)}
                    >
                      Possible Duplicate ({doc.duplicate_count})
                    </button>
                  )}
                  {doc.status === 'failed' && doc.processing_error && (
                    <p className="documents__error-hint">{doc.processing_error}</p>
                  )}
                  <dl className="documents__meta">
                    <div>
                      <dt>Format</dt>
                      <dd>{doc.file_type.toUpperCase()}</dd>
                    </div>
                    <div>
                      <dt>Type</dt>
                      <dd>{renderDocumentType(doc)}</dd>
                    </div>
                    {(doc.has_invoice || doc.has_purchase_order || doc.has_goods_receipt) && doc.vendor_name && (
                      <div>
                        <dt>Vendor</dt>
                        <dd>{doc.vendor_name}</dd>
                      </div>
                    )}
                    <div>
                      <dt>Size</dt>
                      <dd>{formatBytes(doc.file_size)}</dd>
                    </div>
                    <div>
                      <dt>Uploaded</dt>
                      <dd>{formatDate(doc.uploaded_at)}</dd>
                    </div>
                  </dl>
                  {renderActions(doc)}
                  <ProcessingStatus
                    job={processingJobs[doc.id]}
                    onRetry={
                      processingJobs[doc.id]?.status === 'failed'
                        ? () => onRetryProcessing(doc)
                        : undefined
                    }
                    retrying={retryingJobId === processingJobs[doc.id]?.id}
                  />
                </li>
              ))}
            </ul>

            <div className="documents__pagination">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={!hasPrevious || loading}
              >
                Previous
              </button>
              <span>
                Page {page}
                {totalPages > 0 ? ` of ${totalPages}` : ''}
              </span>
              <button
                type="button"
                onClick={() => setPage((current) => current + 1)}
                disabled={!hasNext || loading}
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>

      <DocumentTextModal
        open={viewerOpen}
        title={viewerDoc?.original_filename || 'Document'}
        status={viewerDoc?.status}
        text={viewerText}
        error={viewerError}
        loading={viewerLoading}
        onClose={() => setViewerOpen(false)}
      />

      <InvoiceDataModal
        open={invoiceOpen}
        title={invoiceDoc?.original_filename || 'Invoice'}
        invoice={invoiceData}
        loading={invoiceLoading}
        error={invoiceError}
        onClose={() => setInvoiceOpen(false)}
      />

      <PurchaseOrderDataModal
        open={poOpen}
        title={poDoc?.original_filename || 'Purchase Order'}
        purchaseOrder={poData}
        loading={poLoading}
        error={poError}
        onClose={() => setPoOpen(false)}
      />

      <ClassificationDetailsModal
        open={classificationOpen}
        title={classificationDoc?.original_filename || 'Document'}
        classification={classificationData}
        loading={classificationLoading}
        error={classificationError}
        onClose={() => setClassificationOpen(false)}
      />

      <FieldIntelligenceModal
        open={fieldIntelOpen}
        title={fieldIntelDoc?.original_filename || 'Document'}
        report={fieldIntelReport}
        loading={fieldIntelLoading}
        error={fieldIntelError}
        onClose={() => setFieldIntelOpen(false)}
      />

      <DuplicateDetailsModal
        open={duplicateOpen}
        documentName={duplicateDoc?.original_filename}
        items={duplicateItems}
        loading={duplicateLoading}
        error={duplicateError}
        resolvingId={resolvingDuplicateId}
        onClose={() => setDuplicateOpen(false)}
        onConfirm={
          canResolveDuplicates ? (item) => onResolveDuplicate(item, 'confirmed') : undefined
        }
        onDismiss={
          canResolveDuplicates ? (item) => onResolveDuplicate(item, 'dismissed') : undefined
        }
      />

      <RelationshipsModal
        open={relationshipsOpen}
        documentName={relationshipsDoc?.original_filename}
        relationships={relationships}
        suggestions={relationshipSuggestions}
        loading={relationshipsLoading}
        error={relationshipsError}
        confirmingKey={confirmingRelationshipKey}
        deletingId={deletingRelationshipId}
        onClose={() => setRelationshipsOpen(false)}
        onConfirmSuggestion={canManageRelationships ? onConfirmRelationshipSuggestion : undefined}
        onDelete={canManageRelationships ? onDeleteRelationship : undefined}
      />

      <LineItemsModal
        open={lineItemsOpen}
        title={lineItemsDoc?.original_filename}
        items={lineItems}
        loading={lineItemsLoading}
        error={lineItemsError}
        onClose={() => setLineItemsOpen(false)}
      />
    </div>
  )
}
