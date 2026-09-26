import './DuplicateDetailsModal.css'

const TYPE_LABELS = {
  exact_duplicate: 'Exact duplicate',
  business_duplicate: 'Business duplicate',
  similar_duplicate: 'Similar duplicate',
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatScore(value) {
  if (value === null || value === undefined) return '—'
  return `${Math.round(Number(value) * 100)}%`
}

function typeLabel(value) {
  return TYPE_LABELS[value] || value
}

function DuplicateDetailsModal({
  open,
  documentName,
  items,
  loading,
  error,
  resolvingId,
  onClose,
  onConfirm,
  onDismiss,
}) {
  if (!open) return null

  return (
    <div className="duplicate-modal" role="presentation" onClick={onClose}>
      <div
        className="duplicate-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="duplicate-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="duplicate-modal__header">
          <div>
            <p className="duplicate-modal__eyebrow">Duplicate candidates</p>
            <h2 id="duplicate-modal-title">{documentName || 'Document'}</h2>
          </div>
          <button
            type="button"
            className="duplicate-modal__close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="duplicate-modal__body">
          <p className="duplicate-modal__note">
            Similarity and matching scores are signals only. Confirm or dismiss after human review.
            Documents are never deleted automatically.
          </p>

          {loading && <p className="duplicate-modal__state">Checking duplicates…</p>}
          {!loading && error && (
            <p className="duplicate-modal__state duplicate-modal__state--error">{error}</p>
          )}
          {!loading && !error && (!items || items.length === 0) && (
            <p className="duplicate-modal__state">No duplicate candidates found.</p>
          )}

          {!loading && !error && items?.length > 0 && (
            <ul className="duplicate-modal__list">
              {items.map((item) => (
                <li key={item.id} className="duplicate-modal__item">
                  <div className="duplicate-modal__item-top">
                    <div>
                      <p className="duplicate-modal__filename">
                        {item.matched_filename || item.duplicate_filename || 'Related document'}
                      </p>
                      <p className="duplicate-modal__type">{typeLabel(item.detection_type)}</p>
                    </div>
                    <span className={`duplicate-modal__status duplicate-modal__status--${item.status}`}>
                      {item.status}
                    </span>
                  </div>

                  <dl className="duplicate-modal__grid">
                    <div>
                      <dt>Similarity</dt>
                      <dd>{formatScore(item.similarity_score)}</dd>
                    </div>
                    <div>
                      <dt>Confidence</dt>
                      <dd>{formatScore(item.confidence)}</dd>
                    </div>
                    <div>
                      <dt>Detected</dt>
                      <dd>{formatDate(item.detected_at)}</dd>
                    </div>
                    <div>
                      <dt>Resolved</dt>
                      <dd>{formatDate(item.resolved_at)}</dd>
                    </div>
                  </dl>

                  {Array.isArray(item.reasons) && item.reasons.length > 0 && (
                    <ul className="duplicate-modal__reasons">
                      {item.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  )}

                  <div className="duplicate-modal__actions">
                    {onConfirm && (
                    <button
                      type="button"
                      className="duplicate-modal__action"
                      disabled={resolvingId === item.id || item.status === 'confirmed'}
                      onClick={() => onConfirm(item)}
                    >
                      {resolvingId === item.id && item.status !== 'dismissed'
                        ? 'Saving…'
                        : 'Confirm Duplicate'}
                    </button>
                    )}
                    {onDismiss && (
                    <button
                      type="button"
                      className="duplicate-modal__action duplicate-modal__action--secondary"
                      disabled={resolvingId === item.id || item.status === 'dismissed'}
                      onClick={() => onDismiss(item)}
                    >
                      Dismiss
                    </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

export default DuplicateDetailsModal
