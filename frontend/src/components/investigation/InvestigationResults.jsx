import SQLResultTable from '../ai/SQLResultTable'
import './InvestigationResults.css'

function FindingTypeBadge({ type }) {
  return <span className={`investigation-results__badge investigation-results__badge--${type}`}>{type}</span>
}

function InvestigationResults({ result }) {
  if (!result) return null

  const isUnsupported = result.status === 'unsupported'
  const isFailed = result.status === 'failed'

  return (
    <section className="investigation-results" aria-live="polite">
      <div className="investigation-results__status">
        <h3>Investigation</h3>
        <span className={`investigation-results__status-pill investigation-results__status-pill--${result.status}`}>
          {result.status}
        </span>
      </div>

      {result.summary && <p className="investigation-results__summary">{result.summary}</p>}

      {(isUnsupported || isFailed) && (
        <div className="investigation-results__notice">{result.summary}</div>
      )}

      {!isUnsupported && !isFailed && (
        <>
          <div className="investigation-results__section">
            <h3>Findings</h3>
            {(!result.findings || result.findings.length === 0) && (
              <p className="investigation-results__empty">No findings were produced.</p>
            )}
            <ul className="investigation-results__findings">
              {result.findings?.map((finding, index) => (
                <li key={`${finding.title}-${index}`}>
                  <div className="investigation-results__finding-top">
                    <strong>{finding.title}</strong>
                    <FindingTypeBadge type={finding.type} />
                  </div>
                  <p>{finding.description}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="investigation-results__section">
            <h3>Evidence</h3>
            {(!result.evidence || result.evidence.length === 0) && (
              <p className="investigation-results__empty">No evidence rows were returned.</p>
            )}
            {result.evidence?.map((item, index) => {
              const columns =
                item.data?.length > 0 ? Object.keys(item.data[0]) : []
              return (
                <div key={`${item.step_id || index}`} className="investigation-results__evidence-block">
                  <h4>{item.description}</h4>
                  <SQLResultTable
                    columns={columns}
                    rows={item.data || []}
                    emptyMessage="No rows for this evidence step."
                  />
                </div>
              )
            })}
          </div>
        </>
      )}

      {result.suggested_next_steps?.length > 0 && (
        <div className="investigation-results__section">
          <h3>Suggested next steps</h3>
          <p className="investigation-results__hint">
            Suggestions only — nothing is executed automatically.
          </p>
          <ul className="investigation-results__next-steps">
            {result.suggested_next_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
      )}

      {result.queries?.length > 0 && (
        <details className="investigation-results__technical">
          <summary>Technical Details</summary>
          <ul>
            {result.queries.map((query, index) => (
              <li key={`${query.question}-${index}`}>
                <p>
                  <strong>{query.question}</strong>
                  {typeof query.row_count === 'number' ? ` · ${query.row_count} row(s)` : ''}
                  {query.status ? ` · ${query.status}` : ''}
                </p>
                {query.sql && <pre>{query.sql}</pre>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

export default InvestigationResults
