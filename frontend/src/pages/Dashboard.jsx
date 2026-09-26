import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getAnalyticsSummary,
  getAnomalyAnalytics,
  getDuplicateAnalytics,
  getProcessingAnalytics,
  getReviewAnalytics,
} from '../services/analyticsApi'
import './Dashboard.css'

function MetricCard({ label, value, to, hint }) {
  const content = (
    <>
      <p className="dashboard__metric-label">{label}</p>
      <p className="dashboard__metric-value">{value}</p>
      {hint ? <p className="dashboard__metric-hint">{hint}</p> : null}
    </>
  )
  if (to) {
    return (
      <Link className="dashboard__metric" to={to}>
        {content}
      </Link>
    )
  }
  return <article className="dashboard__metric">{content}</article>
}

function formatCount(value) {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat().format(Number(value) || 0)
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [reviews, setReviews] = useState(null)
  const [processing, setProcessing] = useState(null)
  const [anomalies, setAnomalies] = useState(null)
  const [duplicates, setDuplicates] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summaryData, reviewData, processingData, anomalyData, duplicateData] =
        await Promise.all([
          getAnalyticsSummary(),
          getReviewAnalytics(),
          getProcessingAnalytics(),
          getAnomalyAnalytics(),
          getDuplicateAnalytics(),
        ])
      setSummary(summaryData)
      setReviews(reviewData)
      setProcessing(processingData)
      setAnomalies(anomalyData)
      setDuplicates(duplicateData)
    } catch (err) {
      setError(err.message || 'Failed to load dashboard metrics.')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const hasAnyData =
    summary &&
    (summary.total_documents > 0 ||
      summary.total_invoices > 0 ||
      summary.total_purchase_orders > 0)

  return (
    <div className="dashboard">
      <section className="dashboard__hero">
        <div className="dashboard__hero-copy">
          <p className="dashboard__kicker">Operations</p>
          <h2 className="dashboard__heading">Document &amp; workflow overview</h2>
          <p className="dashboard__lead">
            Live counts from analytics across documents, invoices, purchase orders,
            validation, review, anomalies, and duplicates.
          </p>
        </div>
        <div className="dashboard__hero-panel" aria-hidden="true">
          <div className="dashboard__stack">
            <div className="dashboard__sheet dashboard__sheet--back" />
            <div className="dashboard__sheet dashboard__sheet--mid" />
            <div className="dashboard__sheet dashboard__sheet--front">
              <span />
              <span />
              <span />
            </div>
          </div>
        </div>
      </section>

      {error && <div className="dashboard__error">{error}</div>}

      {loading ? (
        <p className="dashboard__muted">Loading metrics…</p>
      ) : !summary ? (
        <div className="dashboard__empty">
          <h3>Metrics unavailable</h3>
          <p>Sign in with a role that can read analytics, then refresh.</p>
          <button type="button" onClick={load}>
            Retry
          </button>
        </div>
      ) : !hasAnyData ? (
        <div className="dashboard__empty">
          <h3>No operational data yet</h3>
          <p>Upload documents to populate invoices, validations, reviews, and analytics.</p>
          <Link to="/documents">Go to Documents</Link>
        </div>
      ) : (
        <>
          <section className="dashboard__metrics" aria-label="Key metrics">
            <MetricCard
              label="Documents"
              value={formatCount(summary.total_documents)}
              hint={`${formatCount(summary.processed_documents)} processed · ${formatCount(summary.failed_documents)} failed`}
              to="/documents"
            />
            <MetricCard
              label="Invoices"
              value={formatCount(summary.total_invoices)}
              hint={`${formatCount(summary.total_purchase_orders)} POs · ${formatCount(summary.total_goods_receipts)} GRNs`}
              to="/invoices"
            />
            <MetricCard
              label="Vendors / POs"
              value={formatCount(summary.total_purchase_orders)}
              hint="Open vendors and purchase orders"
              to="/vendors"
            />
            <MetricCard
              label="Review queue"
              value={formatCount(summary.documents_requiring_review)}
              hint={
                reviews
                  ? `${formatCount(reviews.pending)} pending · ${formatCount(reviews.in_review)} in review`
                  : undefined
              }
              to="/review-queue"
            />
            <MetricCard
              label="Validations"
              value={formatCount(
                (summary.validation_matched || 0) +
                  (summary.validation_mismatch || 0) +
                  (summary.validation_needs_review || 0),
              )}
              hint={`${formatCount(summary.validation_matched)} matched · ${formatCount(summary.validation_mismatch)} mismatch`}
              to="/validation"
            />
            <MetricCard
              label="Anomalies"
              value={formatCount(summary.anomaly_count)}
              hint={
                anomalies
                  ? `${formatCount(anomalies.requires_review)} need attention`
                  : undefined
              }
              to="/analytics"
            />
            <MetricCard
              label="Duplicates pending"
              value={formatCount(summary.duplicate_pending)}
              hint={
                duplicates
                  ? `${formatCount(duplicates.confirmed)} confirmed · ${formatCount(duplicates.dismissed)} dismissed`
                  : undefined
              }
              to="/documents"
            />
            <MetricCard
              label="Active jobs"
              value={formatCount(summary.active_processing_jobs)}
              hint={
                processing
                  ? `${formatCount(processing.queued)} queued · ${formatCount(processing.running)} running`
                  : undefined
              }
              to="/ingestion"
            />
          </section>

          <section className="dashboard__overview" aria-label="Quick links">
            <article className="dashboard__item">
              <h3>Continue processing</h3>
              <p>
                Upload or ingest documents, then classify and extract invoice/PO/GRN fields from
                Documents.
              </p>
              <Link to="/documents">Documents</Link>
              {' · '}
              <Link to="/ingestion">Ingestion</Link>
            </article>
            <article className="dashboard__item">
              <h3>Human review</h3>
              <p>
                Resolve validation mismatches, field intelligence findings, and duplicate alerts
                in the review queue.
              </p>
              <Link to="/review-queue">Review Queue</Link>
              {' · '}
              <Link to="/validation">Validation</Link>
            </article>
            <article className="dashboard__item">
              <h3>Assistants</h3>
              <p>
                Use RAG, SQL, Investigation, and the Controlled Agent for grounded read-only
                questions.
              </p>
              <Link to="/ai-assistant">AI Assistant</Link>
              {' · '}
              <Link to="/analytics">Analytics</Link>
            </article>
          </section>
        </>
      )}
    </div>
  )
}
