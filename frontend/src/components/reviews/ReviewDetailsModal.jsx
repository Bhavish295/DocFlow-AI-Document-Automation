import { useEffect, useState } from 'react'
import FieldIntelligenceEvidence from './FieldIntelligenceEvidence'
import {
  REASON_LABELS,
  isInvoiceOrPurchaseOrder,
  reasonExplanation,
  reasonLabel,
} from './fieldIntelligencePresentation'
import { getFieldIntelligence } from '../../services/fieldIntelligenceApi'
import './ReviewDetailsModal.css'

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatMoney(value, currency) {
  if (value === null || value === undefined) return '—'
  const amount = Number(value)
  const formatted = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
  return currency ? `${currency} ${formatted}` : formatted
}

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function ReviewDetailsModal({
  open,
  review,
  loading,
  error,
  submitting,
  onClose,
  onStart,
  onApprove,
  onReject,
  intelligenceState = null,
}) {
  const [notes, setNotes] = useState('')
  const [intelligence, setIntelligence] = useState(
    () => intelligenceState || { status: 'idle', report: null, error: '' },
  )

  const documentType = review?.document?.document_type
  const documentId = review?.document?.id
  const showIntelligence = isInvoiceOrPurchaseOrder(documentType)

  useEffect(() => {
    if (!open || !showIntelligence || !documentId) {
      setIntelligence({ status: 'idle', report: null, error: '' })
      return undefined
    }

    let cancelled = false
    setIntelligence({ status: 'loading', report: null, error: '' })
    getFieldIntelligence(documentId)
      .then((report) => {
        if (!cancelled) setIntelligence({ status: 'ready', report, error: '' })
      })
      .catch((err) => {
        if (!cancelled) {
          setIntelligence({
            status: 'error',
            report: null,
            error: err.message || 'Field intelligence could not be loaded.',
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [open, showIntelligence, documentId])

  if (!open) return null

  const resolved = review?.status === 'approved' || review?.status === 'rejected'
  const explanation = reasonExplanation(review?.reason)

  return (
    <div className="review-modal" role="presentation" onClick={onClose}>
      <div
        className="review-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="review-modal__header">
          <div>
            <p className="review-modal__eyebrow">Review details</p>
            <h2 id="review-modal-title">
              {review?.document?.original_filename || 'Document review'}
            </h2>
          </div>
          <button type="button" className="review-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="review-modal__body">
          {loading && <p className="review-modal__state">Loading review…</p>}
          {!loading && error && <p className="review-modal__state review-modal__state--error">{error}</p>}

          {!loading && !error && review && (
            <>
              <section>
                <h3>Document</h3>
                <dl className="review-modal__grid">
                  <div>
                    <dt>Filename</dt>
                    <dd>{displayValue(review.document.original_filename)}</dd>
                  </div>
                  <div>
                    <dt>Type</dt>
                    <dd>{displayValue(review.document.document_type)}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{displayValue(review.document.status)}</dd>
                  </div>
                  <div>
                    <dt>Uploaded</dt>
                    <dd>{formatDate(review.document.uploaded_at)}</dd>
                  </div>
                </dl>
              </section>

              <section>
                <h3>Review</h3>
                <dl className="review-modal__grid">
                  <div className="review-modal__wide">
                    <dt>Reason</dt>
                    <dd>
                      {reasonLabel(review.reason)}
                      {explanation && <p className="review-modal__explanation">{explanation}</p>}
                    </dd>
                  </div>
                  <div>
                    <dt>Priority</dt>
                    <dd>{displayValue(review.priority)}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{displayValue(review.status)}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>{formatDate(review.created_at)}</dd>
                  </div>
                  <div className="review-modal__wide">
                    <dt>Details</dt>
                    <dd>{displayValue(review.details)}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{formatDate(review.updated_at)}</dd>
                  </div>
                </dl>
              </section>

              {review.invoice && (
                <section>
                  <h3>Invoice data</h3>
                  <dl className="review-modal__grid">
                    <div>
                      <dt>Invoice number</dt>
                      <dd>{displayValue(review.invoice.invoice_number)}</dd>
                    </div>
                    <div>
                      <dt>Date</dt>
                      <dd>{displayValue(review.invoice.invoice_date)}</dd>
                    </div>
                    <div>
                      <dt>Vendor</dt>
                      <dd>{displayValue(review.invoice.vendor_name)}</dd>
                    </div>
                    <div>
                      <dt>Subtotal</dt>
                      <dd>{formatMoney(review.invoice.subtotal, review.invoice.currency)}</dd>
                    </div>
                    <div>
                      <dt>Tax</dt>
                      <dd>{formatMoney(review.invoice.tax_amount, review.invoice.currency)}</dd>
                    </div>
                    <div>
                      <dt>Total</dt>
                      <dd>{formatMoney(review.invoice.total_amount, review.invoice.currency)}</dd>
                    </div>
                  </dl>
                </section>
              )}

              {review.purchase_order && (
                <section>
                  <h3>Purchase order data</h3>
                  <dl className="review-modal__grid">
                    <div>
                      <dt>PO number</dt>
                      <dd>{displayValue(review.purchase_order.po_number)}</dd>
                    </div>
                    <div>
                      <dt>Vendor</dt>
                      <dd>{displayValue(review.purchase_order.vendor_name)}</dd>
                    </div>
                    <div>
                      <dt>Subtotal</dt>
                      <dd>
                        {formatMoney(review.purchase_order.subtotal, review.purchase_order.currency)}
                      </dd>
                    </div>
                    <div>
                      <dt>Tax</dt>
                      <dd>
                        {formatMoney(review.purchase_order.tax_amount, review.purchase_order.currency)}
                      </dd>
                    </div>
                    <div>
                      <dt>Total</dt>
                      <dd>
                        {formatMoney(
                          review.purchase_order.total_amount,
                          review.purchase_order.currency,
                        )}
                      </dd>
                    </div>
                  </dl>
                </section>
              )}

              {review.validation && (
                <section>
                  <h3>Validation</h3>
                  <dl className="review-modal__grid">
                    <div>
                      <dt>Status</dt>
                      <dd>{displayValue(review.validation.status)}</dd>
                    </div>
                    <div className="review-modal__wide">
                      <dt>Mismatch summary</dt>
                      <dd>{displayValue(review.validation.mismatch_summary)}</dd>
                    </div>
                  </dl>
                </section>
              )}

              {showIntelligence && (
                <FieldIntelligenceEvidence
                  report={intelligence.report}
                  loading={intelligence.status === 'loading' || intelligence.status === 'idle'}
                  error={intelligence.status === 'error' ? intelligence.error : ''}
                />
              )}

              <section>
                <h3>Reviewer notes</h3>
                <textarea
                  value={notes || review.reviewer_notes || ''}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={4}
                  placeholder="Add notes for this review"
                  disabled={resolved || submitting}
                />
              </section>

              <div className="review-modal__actions">
                {onStart && review.status === 'pending' && (
                  <button type="button" onClick={() => onStart(notes || review.reviewer_notes)} disabled={submitting}>
                    Start Review
                  </button>
                )}
                {onApprove && onReject && !resolved && (
                  <>
                    <button
                      type="button"
                      className="review-modal__approve"
                      onClick={() => onApprove(notes || review.reviewer_notes)}
                      disabled={submitting}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="review-modal__reject"
                      onClick={() => onReject(notes || review.reviewer_notes)}
                      disabled={submitting}
                    >
                      Reject
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default ReviewDetailsModal
export { reasonLabel, REASON_LABELS }
