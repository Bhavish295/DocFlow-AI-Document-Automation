import {
  NO_FIELD_ISSUES_MESSAGE,
  UNAVAILABLE_MESSAGE,
  documentTypeLabel,
  fieldLabel,
  fieldStatusLabel,
  formatConfidence,
  formatFieldValue,
  issueLabel,
  overallStatusLabel,
} from './fieldIntelligencePresentation'

function collectIssueCodes(report) {
  const codes = []
  const push = (issue) => {
    if (!issue || issue === 'extraction_data_missing' || codes.includes(issue)) return
    codes.push(issue)
  }
  for (const issue of report?.issues || []) push(issue)
  for (const field of report?.fields || []) {
    for (const issue of field.issues || []) push(issue)
  }
  return codes
}

function FieldIntelligenceEvidence({ report, loading, error }) {
  const unavailable = report?.overall_status === 'unavailable'
    || report?.issues?.includes('extraction_data_missing')
  const issueCodes = collectIssueCodes(report)

  return (
    <section className="review-modal__intelligence" aria-label="Field Intelligence">
      <h3>Field Intelligence</h3>

      {loading && <p className="review-modal__hint">Checking extracted fields…</p>}

      {!loading && error && (
        <p className="review-modal__hint review-modal__hint--error">{error}</p>
      )}

      {!loading && !error && unavailable && (
        <p className="review-modal__hint">{UNAVAILABLE_MESSAGE}</p>
      )}

      {!loading && !error && report && !unavailable && (
        <>
          <dl className="review-modal__grid">
            <div>
              <dt>Overall Status</dt>
              <dd>{overallStatusLabel(report.overall_status)}</dd>
            </div>
            <div>
              <dt>Overall Confidence</dt>
              <dd>{formatConfidence(report.overall_confidence)}</dd>
            </div>
            <div>
              <dt>Review Required</dt>
              <dd>{report.review_required ? 'Yes' : 'No'}</dd>
            </div>
            <div>
              <dt>Document Type</dt>
              <dd>{documentTypeLabel(report.document_type)}</dd>
            </div>
          </dl>

          {issueCodes.length > 0 ? (
            <div className="review-modal__issue-list">
              <p>Issues</p>
              <ul>
                {issueCodes.map((issue) => (
                  <li key={issue}>{issueLabel(issue)}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="review-modal__hint">{NO_FIELD_ISSUES_MESSAGE}</p>
          )}

          <div className="review-modal__fields">
            {(report.fields || []).map((field) => (
              <article key={field.field_name} className="review-modal__field">
                <h4>{fieldLabel(field.field_name)}</h4>
                <dl>
                  <div>
                    <dt>Value</dt>
                    <dd>{formatFieldValue(field.value, field.status)}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span className={`review-modal__badge review-modal__badge--${field.status || 'missing'}`}>
                        {fieldStatusLabel(field.status)}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt>Confidence</dt>
                    <dd>{formatConfidence(field.confidence)}</dd>
                  </div>
                  <div>
                    <dt>Issues</dt>
                    <dd>
                      {field.issues?.length
                        ? field.issues.map((issue) => issueLabel(issue)).join(' ')
                        : '—'}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  )
}

export default FieldIntelligenceEvidence
