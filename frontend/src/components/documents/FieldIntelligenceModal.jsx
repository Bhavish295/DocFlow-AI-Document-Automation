import {
  UNAVAILABLE_MESSAGE,
  fieldLabel,
  fieldStatusLabel,
  formatConfidence,
  formatFieldValue,
  issueLabel,
  overallStatusLabel,
} from '../reviews/fieldIntelligencePresentation'
import './FieldIntelligenceModal.css'

function FieldIntelligenceModal({ open, title, report, loading, error, onClose }) {
  if (!open) return null

  return (
    <div className="field-intel" role="presentation" onClick={onClose}>
      <div
        className="field-intel__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="field-intel-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="field-intel__header">
          <div>
            <p className="field-intel__eyebrow">Field intelligence</p>
            <h2 id="field-intel-title" className="field-intel__title">
              {title}
            </h2>
          </div>
          <button type="button" className="field-intel__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="field-intel__body">
          {loading && <p className="field-intel__state">Checking extracted fields…</p>}

          {!loading && error && (
            <p className="field-intel__state field-intel__state--error">{error}</p>
          )}

          {!loading && !error && report && (
            <>
              <dl className="field-intel__summary">
                <div>
                  <dt>Overall status</dt>
                  <dd>{overallStatusLabel(report.overall_status)}</dd>
                </div>
                <div>
                  <dt>Overall confidence</dt>
                  <dd>{formatConfidence(report.overall_confidence)}</dd>
                </div>
                <div>
                  <dt>Review required</dt>
                  <dd>{report.review_required ? 'Yes' : 'No'}</dd>
                </div>
              </dl>

              {report.issues?.length > 0 && (
                <p className="field-intel__issues">
                  Issues: {report.issues.map((issue) => issueLabel(issue)).join(', ')}
                </p>
              )}

              {report.fields?.length > 0 ? (
                <div className="field-intel__table-wrap">
                  <table className="field-intel__table">
                    <thead>
                      <tr>
                        <th>Field</th>
                        <th>Value</th>
                        <th>Status</th>
                        <th>Confidence</th>
                        <th>Issues</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.fields.map((field) => (
                        <tr key={field.field_name}>
                          <td data-label="Field">{fieldLabel(field.field_name)}</td>
                          <td data-label="Value">{formatFieldValue(field.value, field.status)}</td>
                          <td data-label="Status">
                            <span className={`field-intel__status field-intel__status--${field.status}`}>
                              {fieldStatusLabel(field.status)}
                            </span>
                          </td>
                          <td data-label="Confidence">{formatConfidence(field.confidence)}</td>
                          <td data-label="Issues">
                            {field.issues?.length
                              ? field.issues.map((issue) => issueLabel(issue)).join(', ')
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="field-intel__state">
                  {report.overall_status === 'unavailable' ? UNAVAILABLE_MESSAGE : 'No extracted invoice or purchase order fields are available for this document.'}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default FieldIntelligenceModal
