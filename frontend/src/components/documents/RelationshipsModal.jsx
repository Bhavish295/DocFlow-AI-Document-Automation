import './RelationshipsModal.css'

const TYPE_LABELS = {
  invoice_purchase_order: 'Invoice → Purchase Order',
  goods_receipt_purchase_order: 'Goods Receipt → Purchase Order',
  invoice_goods_receipt: 'Invoice → Goods Receipt',
}

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

function RelationshipsModal({
  open,
  documentName,
  relationships,
  suggestions,
  loading,
  error,
  confirmingKey,
  deletingId,
  onClose,
  onConfirmSuggestion,
  onDelete,
}) {
  if (!open) return null

  const openSuggestions = (suggestions || []).filter((item) => !item.already_linked)

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
            Relationships are confirmed by a human. Suggestions are not created automatically.
            Full 3-way matching scoring comes in a later step.
          </p>

          {loading && <p className="relationships-modal__state">Loading relationships…</p>}
          {!loading && error && (
            <p className="relationships-modal__state relationships-modal__state--error">{error}</p>
          )}

          {!loading && !error && (
            <>
              <section>
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

              <section>
                <h3>Suggested Relationship</h3>
                {openSuggestions.length === 0 && (
                  <p className="relationships-modal__state">No open suggestions.</p>
                )}
                {openSuggestions.length > 0 && (
                  <ul className="relationships-modal__list">
                    {openSuggestions.map((item) => {
                      const key = `${item.relationship_type}:${item.source_document_id}:${item.target_document_id}`
                      return (
                        <li key={key} className="relationships-modal__item relationships-modal__item--suggested">
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
                              disabled={confirmingKey === key}
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
