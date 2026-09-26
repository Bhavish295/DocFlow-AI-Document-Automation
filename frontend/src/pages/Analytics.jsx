import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Permission } from '../auth/permissions'
import {
  getAnalyticsSummary,
  getAnomalyAnalytics,
  getDocumentAnalytics,
  getDuplicateAnalytics,
  getInvoiceAnalytics,
  getReviewAnalytics,
  getTrendsAnalytics,
  getValidationAnalytics,
  getVendorAnalytics,
} from '../services/analyticsApi'
import {
  getAnomalySummary,
  listAnomalies,
  listAnomalyModelRuns,
  scoreAnomalies,
  trainAnomalyModel,
} from '../services/anomaliesApi'
import './Analytics.css'

const PERIOD_OPTIONS = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
  { value: '12m', label: 'Last 12 Months' },
]

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatScore(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(3)
}

function formatMoney(value, currency) {
  if (value === null || value === undefined) return '—'
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '—'
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency && currency !== 'UNKNOWN' ? currency : 'USD',
      maximumFractionDigits: 2,
    }).format(amount)
  } catch {
    return `${amount.toFixed(2)} ${currency || ''}`.trim()
  }
}

function periodToDates(period) {
  const end = new Date()
  const start = new Date()
  if (period === '7d') start.setUTCDate(start.getUTCDate() - 7)
  else if (period === '90d') start.setUTCDate(start.getUTCDate() - 90)
  else if (period === '12m') start.setUTCDate(start.getUTCDate() - 365)
  else start.setUTCDate(start.getUTCDate() - 30)
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: end.toISOString().slice(0, 10),
  }
}

function BarChart({ title, items, emptyLabel = 'No data' }) {
  const max = Math.max(1, ...items.map((item) => Number(item.count) || 0))
  return (
    <section className="analytics-page__panel analytics-page__chart">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="analytics-page__state">{emptyLabel}</p>
      ) : (
        <ul className="analytics-page__bars">
          {items.map((item) => {
            const count = Number(item.count) || 0
            const width = Math.max(4, Math.round((count / max) * 100))
            return (
              <li key={`${item.name}-${count}`}>
                <div className="analytics-page__bar-label">
                  <span>{item.name || 'unknown'}</span>
                  <strong>{count}</strong>
                </div>
                <div className="analytics-page__bar-track">
                  <div className="analytics-page__bar-fill" style={{ width: `${width}%` }} />
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function TrendChart({ points }) {
  const max = Math.max(
    1,
    ...points.flatMap((point) => [
      point.uploaded_documents || 0,
      point.processed_documents || 0,
      point.invoices || 0,
    ]),
  )
  const sample = points.length > 24
    ? points.filter((_, index) => index % Math.ceil(points.length / 24) === 0)
    : points

  return (
    <section className="analytics-page__panel analytics-page__chart">
      <h3>Document / Invoice Trend</h3>
      {sample.length === 0 ? (
        <p className="analytics-page__state">No trend data for this period.</p>
      ) : (
        <div className="analytics-page__trend">
          {sample.map((point) => (
            <div key={point.period} className="analytics-page__trend-col" title={point.period}>
              <div className="analytics-page__trend-stacks">
                <div
                  className="analytics-page__trend-bar analytics-page__trend-bar--uploaded"
                  style={{ height: `${Math.max(2, ((point.uploaded_documents || 0) / max) * 100)}%` }}
                />
                <div
                  className="analytics-page__trend-bar analytics-page__trend-bar--processed"
                  style={{ height: `${Math.max(2, ((point.processed_documents || 0) / max) * 100)}%` }}
                />
                <div
                  className="analytics-page__trend-bar analytics-page__trend-bar--invoices"
                  style={{ height: `${Math.max(2, ((point.invoices || 0) / max) * 100)}%` }}
                />
              </div>
              <span>{String(point.period).slice(-5)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="analytics-page__legend">
        <span>Uploaded</span>
        <span>Processed</span>
        <span>Invoices</span>
      </div>
    </section>
  )
}

function Analytics() {
  const { can } = useAuth()
  const canTrain = can(Permission.ANOMALIES_TRAIN)
  const canScore = can(Permission.ANOMALIES_SCORE)

  const [period, setPeriod] = useState('30d')
  const [documentType, setDocumentType] = useState('')
  const [currency, setCurrency] = useState('')
  const [vendorPage, setVendorPage] = useState(1)

  const [summary, setSummary] = useState(null)
  const [documents, setDocuments] = useState(null)
  const [invoices, setInvoices] = useState(null)
  const [reviews, setReviews] = useState(null)
  const [validations, setValidations] = useState(null)
  const [anomalyStats, setAnomalyStats] = useState(null)
  const [duplicates, setDuplicates] = useState(null)
  const [trends, setTrends] = useState(null)
  const [vendors, setVendors] = useState(null)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [anomalySummary, setAnomalySummary] = useState(null)
  const [anomalyRows, setAnomalyRows] = useState([])
  const [runs, setRuns] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [vendorFilter, setVendorFilter] = useState('')
  const [confirmTrain, setConfirmTrain] = useState(false)
  const [training, setTraining] = useState(false)
  const [scoring, setScoring] = useState(false)
  const [scoreDocumentId, setScoreDocumentId] = useState('')

  const dateFilters = useMemo(() => periodToDates(period), [period])

  const loadAnalytics = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const common = {
        ...dateFilters,
        document_type: documentType || undefined,
      }
      const [
        summaryPayload,
        documentsPayload,
        invoicesPayload,
        reviewsPayload,
        validationsPayload,
        anomalyPayload,
        duplicatesPayload,
        trendsPayload,
        vendorsPayload,
      ] = await Promise.all([
        getAnalyticsSummary(common),
        getDocumentAnalytics(common),
        getInvoiceAnalytics({ ...dateFilters, currency: currency || undefined }),
        getReviewAnalytics(),
        getValidationAnalytics(),
        getAnomalyAnalytics(),
        getDuplicateAnalytics(),
        getTrendsAnalytics({ period, document_type: documentType || undefined }),
        getVendorAnalytics({
          page: vendorPage,
          page_size: 10,
          currency: currency || undefined,
          ...dateFilters,
        }),
      ])
      setSummary(summaryPayload)
      setDocuments(documentsPayload)
      setInvoices(invoicesPayload)
      setReviews(reviewsPayload)
      setValidations(validationsPayload)
      setAnomalyStats(anomalyPayload)
      setDuplicates(duplicatesPayload)
      setTrends(trendsPayload)
      setVendors(vendorsPayload)
    } catch (err) {
      setError(err.message || 'Failed to load analytics.')
    } finally {
      setLoading(false)
    }
  }, [currency, dateFilters, documentType, period, vendorPage])

  const loadAnomalyTools = useCallback(async () => {
    try {
      const [summaryPayload, anomalyPayload, runsPayload] = await Promise.all([
        getAnomalySummary(),
        listAnomalies({
          page: 1,
          pageSize: 20,
          status: statusFilter || undefined,
          vendor: vendorFilter || undefined,
          sortBy: 'anomaly_score',
          sortOrder: 'desc',
        }),
        listAnomalyModelRuns({ page: 1, pageSize: 5 }),
      ])
      setAnomalySummary(summaryPayload)
      setAnomalyRows(anomalyPayload.items || [])
      setRuns(runsPayload.items || [])
    } catch {
      // Anomaly tooling is secondary; KPI analytics remain primary.
    }
  }, [statusFilter, vendorFilter])

  useEffect(() => {
    loadAnalytics()
  }, [loadAnalytics])

  useEffect(() => {
    loadAnomalyTools()
  }, [loadAnomalyTools])

  const onTrain = async () => {
    setTraining(true)
    setError('')
    setSuccess('')
    try {
      const result = await trainAnomalyModel({})
      if (result.status === 'insufficient_data') {
        setError(
          result.metadata?.message ||
            'Insufficient invoice data to train. Add more invoices with totals and try again.',
        )
      } else if (result.status === 'ready') {
        setSuccess(
          `Model trained successfully on ${result.sample_count} samples (${result.model_name} v${result.model_version}).`,
        )
      } else {
        setError(`Training finished with status: ${result.status}`)
      }
      setConfirmTrain(false)
      await Promise.all([loadAnalytics(), loadAnomalyTools()])
    } catch (err) {
      setError(err.message || 'Training failed.')
    } finally {
      setTraining(false)
    }
  }

  const onScoreRecent = async () => {
    setScoring(true)
    setError('')
    setSuccess('')
    try {
      const result = await scoreAnomalies({ force: false, limit: 50 })
      setSuccess(`Scored ${result.scored} document(s).`)
      await Promise.all([loadAnalytics(), loadAnomalyTools()])
    } catch (err) {
      setError(err.message || 'Scoring failed.')
    } finally {
      setScoring(false)
    }
  }

  const onScoreOne = async (event) => {
    event.preventDefault()
    if (!scoreDocumentId.trim()) return
    setScoring(true)
    setError('')
    setSuccess('')
    try {
      const result = await scoreAnomalies({
        document_id: scoreDocumentId.trim(),
        force: true,
      })
      setSuccess(
        `Document scored as ${result.status} (score ${formatScore(result.anomaly_score)}).`,
      )
      await Promise.all([loadAnalytics(), loadAnomalyTools()])
    } catch (err) {
      setError(err.message || 'Scoring failed.')
    } finally {
      setScoring(false)
    }
  }

  const latest = anomalySummary?.latest_model_run
  const invoiceValueLabel = useMemo(() => {
    const rows = summary?.total_invoice_value_by_currency || []
    if (!rows.length) return '0'
    if (rows.length === 1) return formatMoney(rows[0].total, rows[0].currency)
    return `${rows.length} currencies`
  }, [summary])

  const validationMismatchTotal =
    (summary?.validation_mismatch || 0) + (summary?.validation_needs_review || 0)
  const threeWayMatched = summary?.three_way_matched || 0
  const vendorTotalPages = Math.max(1, Math.ceil((vendors?.total || 0) / (vendors?.page_size || 10)))

  return (
    <div className="analytics-page">
      <section className="analytics-page__intro">
        <p className="analytics-page__kicker">Analytics</p>
        <h2>Operations & Management Reporting</h2>
        <p>
          Read-only KPI and trend reporting across documents, invoices, reviews, validations,
          anomalies, and duplicates. These views support operational awareness and do not make
          financial, fraud, or payment decisions.
        </p>
      </section>

      <form
        className="analytics-page__filters analytics-page__filters--bar"
        onSubmit={(event) => {
          event.preventDefault()
          setVendorPage(1)
          loadAnalytics()
        }}
      >
        <label>
          Date range
          <select
            value={period}
            onChange={(event) => {
              setPeriod(event.target.value)
              setVendorPage(1)
            }}
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Document type
          <select
            value={documentType}
            onChange={(event) => {
              setDocumentType(event.target.value)
              setVendorPage(1)
            }}
          >
            <option value="">All types</option>
            <option value="invoice">Invoice</option>
            <option value="purchase_order">Purchase Order</option>
            <option value="goods_receipt">Goods Receipt</option>
            <option value="contract">Contract</option>
            <option value="receipt">Receipt</option>
            <option value="bank_statement">Bank Statement</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          Currency
          <select
            value={currency}
            onChange={(event) => {
              setCurrency(event.target.value)
              setVendorPage(1)
            }}
          >
            <option value="">All currencies</option>
            <option value="USD">USD</option>
            <option value="PKR">PKR</option>
            <option value="EUR">EUR</option>
            <option value="GBP">GBP</option>
          </select>
        </label>
      </form>

      {error && <div className="analytics-page__alert analytics-page__alert--error">{error}</div>}
      {success && (
        <div className="analytics-page__alert analytics-page__alert--success">{success}</div>
      )}

      {loading ? (
        <div className="analytics-page__state">Loading analytics…</div>
      ) : (
        <>
          <section className="analytics-page__cards">
            <article>
              <h3>Documents</h3>
              <p>{summary?.total_documents ?? 0}</p>
            </article>
            <article>
              <h3>Invoices</h3>
              <p>{summary?.total_invoices ?? 0}</p>
            </article>
            <article>
              <h3>Invoice Value</h3>
              <p>{invoiceValueLabel}</p>
              {(summary?.total_invoice_value_by_currency || []).length > 1 && (
                <small className="analytics-page__muted">Separated by currency</small>
              )}
            </article>
            <article>
              <h3>Review Queue</h3>
              <p>{summary?.documents_requiring_review ?? 0}</p>
            </article>
            <article>
              <h3>Validation Mismatches</h3>
              <p>{validationMismatchTotal}</p>
            </article>
            <article>
              <h3>3-Way Matches</h3>
              <p>{threeWayMatched}</p>
            </article>
            <article>
              <h3>Anomalies</h3>
              <p>{summary?.anomaly_count ?? 0}</p>
            </article>
            <article>
              <h3>Duplicates</h3>
              <p>{summary?.duplicate_pending ?? 0}</p>
            </article>
          </section>

          <section className="analytics-page__report">
            <h3>Management Report</h3>
            <div className="analytics-page__report-grid">
              <div>
                <h4>Operational Overview</h4>
                <ul>
                  <li>
                    Processing health: {summary?.processed_documents ?? 0} processed,{' '}
                    {summary?.failed_documents ?? 0} failed,{' '}
                    {summary?.active_processing_jobs ?? 0} active jobs
                  </li>
                  <li>Review workload: {summary?.documents_requiring_review ?? 0} requiring review</li>
                  <li>
                    Validation health: {summary?.validation_matched ?? 0} matched,{' '}
                    {summary?.validation_mismatch ?? 0} mismatch,{' '}
                    {summary?.validation_needs_review ?? 0} needs review
                  </li>
                </ul>
              </div>
              <div>
                <h4>Financial Overview</h4>
                <ul>
                  <li>Invoice count: {summary?.total_invoices ?? 0}</li>
                  {(summary?.total_invoice_value_by_currency || []).length === 0 && (
                    <li>Invoice values: none</li>
                  )}
                  {(summary?.total_invoice_value_by_currency || []).map((row) => (
                    <li key={row.currency}>
                      {row.currency}: {formatMoney(row.total, row.currency)} ({row.count} invoices)
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Risk Signals</h4>
                <ul>
                  <li>Anomaly findings: {summary?.anomaly_count ?? 0}</li>
                  <li>Duplicate findings pending: {summary?.duplicate_pending ?? 0}</li>
                  <li>Validation mismatches: {summary?.validation_mismatch ?? 0}</li>
                </ul>
              </div>
            </div>
          </section>

          <div className="analytics-page__charts">
            <BarChart title="Document Types" items={documents?.by_type || []} />
            <BarChart title="Document Status" items={documents?.by_status || []} />
            <TrendChart points={trends?.points || []} />
            <BarChart
              title="Invoice Currency Breakdown"
              items={(invoices?.by_currency || []).map((row) => ({
                name: `${row.currency} (${formatMoney(row.total, row.currency)})`,
                count: row.count,
              }))}
            />
            <BarChart
              title="Validation Results"
              items={[
                { name: 'matched', count: validations?.invoice_po?.matched || 0 },
                { name: 'mismatch', count: validations?.invoice_po?.mismatch || 0 },
                { name: 'needs_review', count: validations?.invoice_po?.needs_review || 0 },
                { name: '3way matched', count: validations?.three_way?.matched || 0 },
                { name: '3way mismatch', count: validations?.three_way?.mismatch || 0 },
                { name: '3way needs_review', count: validations?.three_way?.needs_review || 0 },
              ]}
            />
            <BarChart
              title="Review Status"
              items={[
                { name: 'pending', count: reviews?.pending || 0 },
                { name: 'in_review', count: reviews?.in_review || 0 },
                { name: 'approved', count: reviews?.approved || 0 },
                { name: 'rejected', count: reviews?.rejected || 0 },
              ]}
            />
            <BarChart
              title="Anomaly Status"
              items={[
                { name: 'normal', count: anomalyStats?.normal || 0 },
                { name: 'unusual', count: anomalyStats?.unusual || 0 },
                { name: 'anomaly', count: anomalyStats?.anomaly || 0 },
                { name: 'requires_review', count: anomalyStats?.requires_review || 0 },
              ]}
            />
            <BarChart
              title="Duplicate Status"
              items={[
                { name: 'exact', count: duplicates?.exact_duplicate || 0 },
                { name: 'business', count: duplicates?.business_duplicate || 0 },
                { name: 'similar', count: duplicates?.similar_duplicate || 0 },
                { name: 'pending', count: duplicates?.pending || 0 },
                { name: 'confirmed', count: duplicates?.confirmed || 0 },
                { name: 'dismissed', count: duplicates?.dismissed || 0 },
              ]}
            />
          </div>

          <section className="analytics-page__panel">
            <div className="analytics-page__panel-head">
              <h3>Vendor Report</h3>
              <p className="analytics-page__muted">
                One row per vendor + currency. Values are never mixed across currencies.
              </p>
            </div>
            {!vendors?.items?.length ? (
              <p className="analytics-page__state">No vendor invoice analytics yet.</p>
            ) : (
              <>
                <div className="analytics-page__table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Vendor</th>
                        <th>Invoice Count</th>
                        <th>Total Value</th>
                        <th>Currency</th>
                        <th>Average Invoice</th>
                        <th>Validation Issues</th>
                        <th>Review Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {vendors.items.map((row) => (
                        <tr key={`${row.vendor}-${row.currency}-${row.vendor_id || 'x'}`}>
                          <td>{row.vendor}</td>
                          <td>{row.invoice_count}</td>
                          <td>{formatMoney(row.total_value, row.currency)}</td>
                          <td>{row.currency}</td>
                          <td>{formatMoney(row.average_invoice, row.currency)}</td>
                          <td>{row.validation_issues}</td>
                          <td>{row.review_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="analytics-page__pager">
                  <button
                    type="button"
                    disabled={vendorPage <= 1}
                    onClick={() => setVendorPage((page) => page - 1)}
                  >
                    Previous
                  </button>
                  <span>
                    Page {vendorPage} of {vendorTotalPages}
                  </span>
                  <button
                    type="button"
                    disabled={vendorPage >= vendorTotalPages}
                    onClick={() => setVendorPage((page) => page + 1)}
                  >
                    Next
                  </button>
                </div>
              </>
            )}
          </section>

          <section className="analytics-page__intro analytics-page__anomaly-intro">
            <h2>Anomaly Detection Tools</h2>
            <p>
              Local IsolationForest scoring for unusual invoice patterns. Scores indicate
              unusualness relative to historical data — not fraud determinations.
            </p>
          </section>

          {(canTrain || canScore) && (
            <section className="analytics-page__actions">
              {canTrain && (
                <button type="button" onClick={() => setConfirmTrain(true)} disabled={training}>
                  Train Model
                </button>
              )}
              {canScore && (
                <button type="button" onClick={onScoreRecent} disabled={scoring || !latest}>
                  {scoring ? 'Scoring…' : 'Score Recent Invoices'}
                </button>
              )}
            </section>
          )}

          <section className="analytics-page__cards">
            <article>
              <h3>Model status</h3>
              <p>{latest?.status || 'No ready model'}</p>
            </article>
            <article>
              <h3>Last training run</h3>
              <p>{formatDate(latest?.trained_at || latest?.created_at)}</p>
            </article>
            <article>
              <h3>Training samples</h3>
              <p>{latest?.sample_count ?? 0}</p>
            </article>
            <article>
              <h3>Analyzed documents</h3>
              <p>{anomalySummary?.analyzed_documents ?? 0}</p>
            </article>
            <article>
              <h3>Needs attention</h3>
              <p>{anomalySummary?.anomalies_requiring_attention ?? 0}</p>
            </article>
          </section>

          {canScore && (
            <section className="analytics-page__panel">
              <h3>Score a document</h3>
              <form onSubmit={onScoreOne} className="analytics-page__score-form">
                <input
                  value={scoreDocumentId}
                  onChange={(event) => setScoreDocumentId(event.target.value)}
                  placeholder="Document UUID"
                />
                <button type="submit" disabled={scoring || !scoreDocumentId.trim()}>
                  Analyze
                </button>
              </form>
            </section>
          )}

          <section className="analytics-page__panel">
            <div className="analytics-page__panel-head">
              <h3>Recent anomalies</h3>
              <div className="analytics-page__filters">
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">All statuses</option>
                  <option value="normal">normal</option>
                  <option value="unusual">unusual</option>
                  <option value="anomaly">anomaly</option>
                  <option value="requires_review">requires_review</option>
                </select>
                <input
                  value={vendorFilter}
                  onChange={(event) => setVendorFilter(event.target.value)}
                  placeholder="Filter vendor"
                />
              </div>
            </div>

            {anomalyRows.length === 0 ? (
              <p className="analytics-page__state">No anomaly results yet. Train and score invoices.</p>
            ) : (
              <div className="analytics-page__table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Vendor</th>
                      <th>Score</th>
                      <th>Status</th>
                      <th>Reasons</th>
                      <th>Detected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalyRows.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.filename || '—'}</strong>
                          <div className="analytics-page__muted">
                            {item.invoice_number || item.document_id}
                          </div>
                        </td>
                        <td>{item.vendor_name || '—'}</td>
                        <td>{formatScore(item.anomaly_score)}</td>
                        <td>
                          <span className={`analytics-page__badge analytics-page__badge--${item.status}`}>
                            {item.status}
                          </span>
                        </td>
                        <td>
                          <ul className="analytics-page__reasons">
                            {(item.reasons || []).slice(0, 3).map((reason) => (
                              <li key={reason}>{reason}</li>
                            ))}
                          </ul>
                        </td>
                        <td>{formatDate(item.detected_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="analytics-page__panel">
            <h3>Model runs</h3>
            {runs.length === 0 ? (
              <p className="analytics-page__state">No training runs yet.</p>
            ) : (
              <ul className="analytics-page__runs">
                {runs.map((run) => (
                  <li key={run.id}>
                    <strong>
                      {run.model_name} v{run.model_version}
                    </strong>
                    <span>{run.status}</span>
                    <span>{run.sample_count} samples</span>
                    <span>{formatDate(run.trained_at || run.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {anomalySummary?.disclaimer && (
            <p className="analytics-page__disclaimer">{anomalySummary.disclaimer}</p>
          )}
        </>
      )}

      {confirmTrain && (
        <div className="analytics-page__modal-backdrop" role="presentation">
          <div className="analytics-page__modal" role="dialog" aria-modal="true">
            <h3>Train anomaly model?</h3>
            <p>
              The model learns statistical patterns from existing invoice totals and vendor history
              using a local IsolationForest. It does not call external AI services and does not
              label invoices as fraudulent.
            </p>
            <div className="analytics-page__modal-actions">
              <button type="button" onClick={() => setConfirmTrain(false)}>
                Cancel
              </button>
              <button type="button" onClick={onTrain} disabled={training}>
                {training ? 'Training…' : 'Confirm Train'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Analytics
