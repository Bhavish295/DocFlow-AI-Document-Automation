import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Permission } from '../auth/permissions'
import ReviewDetailsModal, { reasonLabel } from '../components/reviews/ReviewDetailsModal'
import {
  approveReview,
  getReview,
  listReviews,
  rejectReview,
  startReview,
} from '../services/reviewsApi'
import './ReviewQueue.css'

const PAGE_SIZE = 20

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function ReviewQueue() {
  const { can } = useAuth()
  const canReview = can(Permission.REVIEWS_WRITE)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrevious, setHasPrevious] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [reason, setReason] = useState('')
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState('')
  const [detailsReview, setDetailsReview] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const loadReviews = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const payload = await listReviews({
        page,
        pageSize: PAGE_SIZE,
        status: status || undefined,
        priority: priority || undefined,
        reason: reason || undefined,
      })
      setItems(payload.items || [])
      setTotal(payload.total || 0)
      setTotalPages(payload.total_pages || 0)
      setHasNext(Boolean(payload.has_next))
      setHasPrevious(Boolean(payload.has_previous))
    } catch (err) {
      setError(err.message || 'Failed to load reviews.')
    } finally {
      setLoading(false)
    }
  }, [page, status, priority, reason])

  useEffect(() => {
    loadReviews()
  }, [loadReviews])

  const applyFilters = (event) => {
    event.preventDefault()
    setPage(1)
    loadReviews()
  }

  const clearFilters = () => {
    setStatus('')
    setPriority('')
    setReason('')
    setPage(1)
  }

  const openDetails = async (reviewId) => {
    setDetailsOpen(true)
    setDetailsLoading(true)
    setDetailsError('')
    setDetailsReview(null)
    try {
      const payload = await getReview(reviewId)
      setDetailsReview(payload)
    } catch (err) {
      setDetailsError(err.message || 'Failed to load review details.')
    } finally {
      setDetailsLoading(false)
    }
  }

  const runAction = async (action, notes) => {
    if (!detailsReview) return
    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const payload = { reviewer_notes: notes || null }
      let result
      if (action === 'start') result = await startReview(detailsReview.id, payload)
      if (action === 'approve') result = await approveReview(detailsReview.id, payload)
      if (action === 'reject') result = await rejectReview(detailsReview.id, payload)
      setDetailsReview(result)
      setSuccess(`Review ${action === 'start' ? 'started' : `${action}d`}.`)
      await loadReviews()
    } catch (err) {
      setError(err.message || 'Review action failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const quickAction = async (review, action) => {
    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      if (action === 'start') await startReview(review.id, {})
      if (action === 'approve') await approveReview(review.id, {})
      if (action === 'reject') await rejectReview(review.id, {})
      setSuccess(`Review ${action === 'start' ? 'started' : `${action}d`}.`)
      await loadReviews()
    } catch (err) {
      setError(err.message || 'Review action failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="review-queue">
      <section className="review-queue__intro">
        <div>
          <p className="review-queue__kicker">Human review</p>
          <h2 className="review-queue__title">Review Queue</h2>
          <p className="review-queue__desc">
            Documents that need manual verification appear here based on failed processing,
            uncertain classification, low extraction confidence, missing or invalid fields,
            financial inconsistencies, or validation mismatches.
          </p>
        </div>
      </section>

      <section className="review-queue__filters">
        <form className="review-queue__filters-form" onSubmit={applyFilters}>
          <label>
            Status
            <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}>
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="in_review">In Review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label>
            Priority
            <select value={priority} onChange={(event) => { setPriority(event.target.value); setPage(1) }}>
              <option value="">All priorities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </label>
          <label>
            Reason
            <select value={reason} onChange={(event) => { setReason(event.target.value); setPage(1) }}>
              <option value="">All reasons</option>
              <option value="processing_failed">Processing Failed</option>
              <option value="unknown_document_type">Unknown Document Type</option>
              <option value="low_classification_confidence">Low Classification Confidence</option>
              <option value="low_extraction_confidence">Low Extraction Confidence</option>
              <option value="missing_required_fields">Missing Required Fields</option>
              <option value="validation_mismatch">Invoice vs PO Validation Mismatch</option>
              <option value="field_missing">Missing Extracted Fields</option>
              <option value="field_invalid">Invalid Extracted Fields</option>
              <option value="field_suspicious">Fields Need Verification</option>
              <option value="financial_consistency_mismatch">Financial Consistency Mismatch</option>
              <option value="classification_model_disagreement">Classification Model Disagreement</option>
              <option value="three_way_match_mismatch">3-Way Match Mismatch</option>
              <option value="three_way_match_needs_review">3-Way Match Needs Review</option>
            </select>
          </label>
          <div className="review-queue__filters-actions">
            <button type="button" onClick={clearFilters}>Clear Filters</button>
          </div>
        </form>
      </section>

      {error && <div className="review-queue__alert review-queue__alert--error">{error}</div>}
      {success && <div className="review-queue__alert review-queue__alert--success">{success}</div>}

      <section className="review-queue__list">
        <div className="review-queue__list-header">
          <h3>Queue</h3>
          <p>{loading ? 'Loading…' : `${total} review${total === 1 ? '' : 's'}`}</p>
        </div>

        {loading && <div className="review-queue__state">Loading review queue…</div>}

        {!loading && items.length === 0 && (
          <div className="review-queue__state">No review items match the current filters.</div>
        )}

        {!loading && items.length > 0 && (
          <>
            <div className="review-queue__table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Reason</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className="review-queue__doc">
                          <strong>{item.document_filename || 'Document'}</strong>
                          <span>{item.document_type || '—'}</span>
                        </div>
                      </td>
                      <td>{reasonLabel(item.reason)}</td>
                      <td>
                        <span className={`review-queue__priority review-queue__priority--${item.priority}`}>
                          {item.priority}
                        </span>
                      </td>
                      <td>
                        <span className={`review-queue__status review-queue__status--${item.status}`}>
                          {item.status.replaceAll('_', ' ')}
                        </span>
                      </td>
                      <td>{formatDate(item.created_at)}</td>
                      <td>
                        <div className="review-queue__actions">
                          <button type="button" onClick={() => openDetails(item.id)}>View</button>
                          {canReview && item.status === 'pending' && (
                            <button type="button" onClick={() => quickAction(item, 'start')} disabled={submitting}>
                              Start Review
                            </button>
                          )}
                          {canReview && item.status !== 'approved' && item.status !== 'rejected' && (
                            <>
                              <button type="button" onClick={() => quickAction(item, 'approve')} disabled={submitting}>
                                Approve
                              </button>
                              <button type="button" onClick={() => quickAction(item, 'reject')} disabled={submitting}>
                                Reject
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="review-queue__cards">
              {items.map((item) => (
                <li key={item.id}>
                  <div className="review-queue__card-top">
                    <div>
                      <strong>{item.document_filename || 'Document'}</strong>
                      <p>{reasonLabel(item.reason)}</p>
                    </div>
                    <span className={`review-queue__status review-queue__status--${item.status}`}>
                      {item.status.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <div className="review-queue__actions">
                    <button type="button" onClick={() => openDetails(item.id)}>View</button>
                    {canReview && item.status === 'pending' && (
                      <button type="button" onClick={() => quickAction(item, 'start')} disabled={submitting}>
                        Start Review
                      </button>
                    )}
                    {canReview && item.status !== 'approved' && item.status !== 'rejected' && (
                      <>
                        <button type="button" onClick={() => quickAction(item, 'approve')} disabled={submitting}>
                          Approve
                        </button>
                        <button type="button" onClick={() => quickAction(item, 'reject')} disabled={submitting}>
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>

            <div className="review-queue__pagination">
              <button type="button" disabled={!hasPrevious || loading} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                Previous
              </button>
              <span>
                Page {page}
                {totalPages > 0 ? ` of ${totalPages}` : ''}
              </span>
              <button type="button" disabled={!hasNext || loading} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          </>
        )}
      </section>

      <ReviewDetailsModal
        open={detailsOpen}
        review={detailsReview}
        loading={detailsLoading}
        error={detailsError}
        submitting={submitting}
        onClose={() => setDetailsOpen(false)}
        onStart={canReview ? (notes) => runAction('start', notes) : undefined}
        onApprove={canReview ? (notes) => runAction('approve', notes) : undefined}
        onReject={canReview ? (notes) => runAction('reject', notes) : undefined}
      />
    </div>
  )
}

export default ReviewQueue
