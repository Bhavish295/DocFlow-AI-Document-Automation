import { useEffect, useMemo, useState } from 'react'
import { listDocuments } from '../../services/documentsApi'
import './RelationshipsModal.css'

const TYPE_LABELS = {
  invoice_purchase_order: 'Invoice → Purchase Order',
  goods_receipt_purchase_order: 'Goods Receipt → Purchase Order',
  invoice_goods_receipt: 'Invoice → Goods Receipt',
}

const RELATIONSHIP_OPTIONS = [
  {
    value: 'invoice_purchase_order',
    label: 'Invoice → Purchase Order',
    sourceType: 'invoice',
    targetType: 'purchase_order',
  },
  {
    value: 'goods_receipt_purchase_order',
    label: 'Goods Receipt → Purchase Order',
    sourceType: 'goods_receipt',
    targetType: 'purchase_order',
  },
  {
    value: 'invoice_goods_receipt',
    label: 'Invoice → Goods Receipt',
    sourceType: 'invoice',
    targetType: 'goods_receipt',
  },
]

const DOC_TYPE_LABELS = {
  invoice: 'Invoice',
  purchase_order: 'Purchase Order',
  goods_receipt: 'Goods Receipt',
  contract: 'Contract',
  receipt: 'Receipt',
  bank_statement: 'Bank Statement',
  other: 'Other',
}

function typeLabel(value) {
  return TYPE_LABELS[value] || value
}

function docTypeLabel(value) {
  return DOC_TYPE_LABELS[value] || value || '—'
}

function optionsForDocumentType(documentType) {
  return RELATIONSHIP_OPTIONS.filter(
    (option) =>
      option.sourceType === documentType || option.targetType === documentType,
  )
}

function relatedDocumentType(currentType, option) {
  if (!option) return null
  return currentType === option.sourceType ? option.targetType : option.sourceType
}

function buildCreatePayload(currentDoc, relatedId, option) {
  if (currentDoc.document_type === option.sourceType) {
    return {
      source_document_id: currentDoc.id,
      target_document_id: relatedId,
      relationship_type: option.value,
    }
  }
  return {
    source_document_id: relatedId,
    target_document_id: currentDoc.id,
    relationship_type: option.value,
  }
}

function isAlreadyLinked(relationships, currentDocId, relatedId, relationshipType) {
  return (relationships || []).some((item) => {
    if (item.relationship_type !== relationshipType) return false
    const pair = new Set([
      String(item.source_document_id),
      String(item.target_document_id),
    ])
    return pair.has(String(currentDocId)) && pair.has(String(relatedId))
  })
}

function RelationshipsModal({
  open,
  sourceDocument,
  documentName,
  relationships,
  suggestions,
  loading,
  error,
  successMessage,
  confirmingKey,
  creating,
  deletingId,
  canCreate,
  onClose,
  onConfirmSuggestion,
  onCreateRelationship,
  onDelete,
}) {
  const [relationshipType, setRelationshipType] = useState('')
  const [relatedDocumentId, setRelatedDocumentId] = useState('')
  const [candidates, setCandidates] = useState([])
  const [candidatesLoading, setCandidatesLoading] = useState(false)
  const [candidatesError, setCandidatesError] = useState('')
  const [formError, setFormError] = useState('')

  const availableOptions = useMemo(
    () => optionsForDocumentType(sourceDocument?.document_type),
    [sourceDocument?.document_type],
  )

  const selectedOption = useMemo(
    () => availableOptions.find((item) => item.value === relationshipType) || null,
    [availableOptions, relationshipType],
  )

  const neededRelatedType = relatedDocumentType(
    sourceDocument?.document_type,
    selectedOption,
  )

  useEffect(() => {
    if (!open) {
      setRelationshipType('')
      setRelatedDocumentId('')
      setCandidates([])
      setCandidatesError('')
      setFormError('')
      return
    }
    if (availableOptions.length === 1) {
      setRelationshipType(availableOptions[0].value)
    }
  }, [open, availableOptions])

  useEffect(() => {
    if (!open || !neededRelatedType || !sourceDocument?.id) {
      setCandidates([])
      return
    }

    let cancelled = false
    const loadCandidates = async () => {
      setCandidatesLoading(true)
      setCandidatesError('')
      setRelatedDocumentId('')
      try {
        const data = await listDocuments({
          page: 1,
          pageSize: 100,
          documentType: neededRelatedType,
          sortBy: 'uploaded_at',
          sortOrder: 'desc',
        })
        if (cancelled) return
        const items = (data.items || []).filter(
          (doc) =>
            String(doc.id) !== String(sourceDocument.id) &&
            !isAlreadyLinked(
              relationships,
              sourceDocument.id,
              doc.id,
              selectedOption?.value,
            ),
        )
        setCandidates(items)
      } catch (err) {
        if (!cancelled) {
          setCandidates([])
          setCandidatesError(err.message || 'Failed to load related documents.')
        }
      } finally {
        if (!cancelled) setCandidatesLoading(false)
      }
    }

    loadCandidates()
    return () => {
      cancelled = true
    }
  }, [
    open,
    neededRelatedType,
    sourceDocument?.id,
    relationships,
    selectedOption?.value,
  ])

  if (!open) return null

  const openSuggestions = (suggestions || []).filter((item) => !item.already_linked)

  const onSubmitCreate = async (event) => {
    event.preventDefault()
    setFormError('')
    if (!canCreate || !onCreateRelationship || !sourceDocument || !selectedOption) {
      return
    }
    if (!relatedDocumentId) {
      setFormError('Select a related document.')
      return
    }
    try {
      await onCreateRelationship(
        buildCreatePayload(sourceDocument, relatedDocumentId, selectedOption),
      )
      setRelatedDocumentId('')
    } catch (err) {
      setFormError(err.message || 'Could not create relationship.')
    }
  }

  return (
    <div className="relationships-modal" role="presentation" onClick={onClose}>
      <div
        className="relationships-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="relationships-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="relationships-modal__header">
          <div>
            <p className="relationships-modal__eyebrow">Document relationships</p>
            <h2 id="relationships-modal-title">{documentName || 'Document'}</h2>
            {sourceDocument?.document_type && (
              <p className="relationships-modal__subtitle">
                Current type: {docTypeLabel(sourceDocument.document_type)}
              </p>
            )}
          </div>
          <button
            type="button"
            className="relationships-modal__close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="relationships-modal__body">
          <p className="relationships-modal__note">
            Relationships must be confirmed by a human. Suggestions are assistive only and
            are never created automatically.
          </p>

          {loading && <p className="relationships-modal__state">Loading relationships…</p>}
          {!loading && error && (
            <p className="relationships-modal__state relationships-modal__state--error">{error}</p>
          )}
          {!loading && successMessage && (
            <p className="relationships-modal__state relationships-modal__state--success">
              {successMessage}
            </p>
          )}

          {!loading && (
            <>
              <section className="relationships-modal__section">
                <h3>Related Documents</h3>
                {(!relationships || relationships.length === 0) && (
                  <p className="relationships-modal__state">No confirmed relationships yet.</p>
                )}
                {relationships?.length > 0 && (
                  <ul className="relationships-modal__list">
                    {relationships.map((item) => (
                      <li key={item.id} className="relationships-modal__item">
                        <div className="relationships-modal__item-top">
                          <div>
                            <p className="relationships-modal__filename">
                              {item.related_filename ||
                                item.target_filename ||
                                item.source_filename ||
                                'Related document'}
                            </p>
                            <p className="relationships-modal__type">
                              {docTypeLabel(item.related_document_type || item.target_document_type)}
                            </p>
                          </div>
                          <span className="relationships-modal__status">{item.status}</span>
                        </div>
                        <dl className="relationships-modal__grid">
                          <div>
                            <dt>Relationship</dt>
                            <dd>{item.display_label || typeLabel(item.relationship_type)}</dd>
                          </div>
                          <div>
                            <dt>Match key</dt>
                            <dd>{item.match_key || '—'}</dd>
                          </div>
                        </dl>
                        <div className="relationships-modal__actions">
                          {onDelete && (
                            <button
                              type="button"
                              className="relationships-modal__danger"
                              disabled={deletingId === item.id}
                              onClick={() => onDelete(item)}
                            >
                              {deletingId === item.id ? 'Removing…' : 'Remove'}
                            </button>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {canCreate && onCreateRelationship && (
                <section className="relationships-modal__section relationships-modal__section--form">
                  <h3>Add Relationship</h3>
                  <p className="relationships-modal__hint">
                    Manually confirm a link between this document and another classified
                    invoice, purchase order, or goods receipt.
                  </p>

                  {availableOptions.length === 0 ? (
                    <p className="relationships-modal__state">
                      Manual linking is available when this document is classified as an
                      invoice, purchase order, or goods receipt.
                    </p>
                  ) : (
                    <form className="relationships-modal__form" onSubmit={onSubmitCreate}>
                      <label>
                        Relationship type
                        <select
                          value={relationshipType}
                          onChange={(event) => {
                            setRelationshipType(event.target.value)
                            setRelatedDocumentId('')
                            setFormError('')
                          }}
                          required
                        >
                          <option value="">Select type…</option>
                          {availableOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Related document
                        <select
                          value={relatedDocumentId}
                          onChange={(event) => {
                            setRelatedDocumentId(event.target.value)
                            setFormError('')
                          }}
                          disabled={!selectedOption || candidatesLoading}
                          required
                        >
                          <option value="">
                            {candidatesLoading
                              ? 'Loading documents…'
                              : selectedOption
                                ? `Select ${docTypeLabel(neededRelatedType).toLowerCase()}…`
                                : 'Select a relationship type first…'}
                          </option>
                          {candidates.map((doc) => (
                            <option key={doc.id} value={doc.id}>
                              {doc.original_filename}
                            </option>
                          ))}
                        </select>
                      </label>

                      {candidatesError && (
                        <p className="relationships-modal__state relationships-modal__state--error">
                          {candidatesError}
                        </p>
                      )}
                      {!candidatesLoading &&
                        selectedOption &&
                        !candidatesError &&
                        candidates.length === 0 && (
                          <p className="relationships-modal__state">
                            No eligible {docTypeLabel(neededRelatedType).toLowerCase()}{' '}
                            documents available to link.
                          </p>
                        )}
                      {formError && (
                        <p className="relationships-modal__state relationships-modal__state--error">
                          {formError}
                        </p>
                      )}

                      <div className="relationships-modal__form-actions">
                        <button
                          type="submit"
                          className="relationships-modal__confirm relationships-modal__confirm--primary"
                          disabled={
                            creating ||
                            !selectedOption ||
                            !relatedDocumentId ||
                            candidatesLoading
                          }
                        >
                          {creating ? 'Creating…' : 'Confirm relationship'}
                        </button>
                      </div>
                    </form>
                  )}
                </section>
              )}

              <section className="relationships-modal__section">
                <h3>Suggested Relationship</h3>
                {openSuggestions.length === 0 && (
                  <p className="relationships-modal__state">No open suggestions.</p>
                )}
                {openSuggestions.length > 0 && (
                  <ul className="relationships-modal__list">
                    {openSuggestions.map((item) => {
                      const key = `${item.relationship_type}:${item.source_document_id}:${item.target_document_id}`
                      return (
                        <li
                          key={key}
                          className="relationships-modal__item relationships-modal__item--suggested"
                        >
                          <div className="relationships-modal__item-top">
                            <div>
                              <p className="relationships-modal__filename">
                                {item.target_filename || item.source_filename || 'Candidate'}
                              </p>
                              <p className="relationships-modal__type">
                                Suggested · {typeLabel(item.relationship_type)}
                              </p>
                            </div>
                            <span className="relationships-modal__status relationships-modal__status--suggested">
                              suggested
                            </span>
                          </div>
                          <dl className="relationships-modal__grid">
                            <div>
                              <dt>Match key</dt>
                              <dd>{item.match_key || '—'}</dd>
                            </div>
                            <div>
                              <dt>Field</dt>
                              <dd>{item.match_field || '—'}</dd>
                            </div>
                          </dl>
                          <div className="relationships-modal__actions">
                            {onConfirmSuggestion && (
                              <button
                                type="button"
                                className="relationships-modal__confirm"
                                disabled={confirmingKey === key || creating}
                                onClick={() => onConfirmSuggestion(item)}
                              >
                                {confirmingKey === key ? 'Confirming…' : 'Confirm relationship'}
                              </button>
                            )}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default RelationshipsModal
