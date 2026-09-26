import './ClassificationDetailsModal.css'

function formatConfidence(value) {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${Math.round(numeric * 100)}%`
}

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  return String(value).replaceAll('_', ' ')
}

function ClassificationDetailsModal({ open, title, classification, loading, error, onClose }) {
  if (!open) return null

  return (
    <div className="classification-modal" role="presentation" onClick={onClose}>
      <div
        className="classification-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="classification-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="classification-modal__header">
          <div>
            <p className="classification-modal__eyebrow">Classification</p>
            <h2 id="classification-modal-title">{title}</h2>
          </div>
          <button type="button" className="classification-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="classification-modal__body">
          {loading && <p className="classification-modal__state">Loading classification…</p>}
          {!loading && error && (
            <p className="classification-modal__state classification-modal__state--error">{error}</p>
          )}
          {!loading && !error && classification && (
            <dl className="classification-modal__grid">
              <div>
                <dt>Final type</dt>
                <dd>{displayValue(classification.final_type || classification.document_type)}</dd>
              </div>
              <div>
                <dt>Final confidence</dt>
                <dd>{formatConfidence(classification.final_confidence ?? classification.confidence)}</dd>
              </div>
              <div>
                <dt>Method</dt>
                <dd>{displayValue(classification.classification_method)}</dd>
              </div>
              <div>
                <dt>Rule-based prediction</dt>
                <dd>
                  {displayValue(classification.rule_based_type)}
                  {' · '}
                  {formatConfidence(classification.rule_based_confidence)}
                </dd>
              </div>
              <div>
                <dt>ML prediction</dt>
                <dd>
                  {displayValue(classification.ml_type)}
                  {' · '}
                  {formatConfidence(classification.ml_confidence)}
                </dd>
              </div>
            </dl>
          )}
        </div>
      </div>
    </div>
  )
}

export default ClassificationDetailsModal
