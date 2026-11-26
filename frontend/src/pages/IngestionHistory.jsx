import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Permission } from '../auth/permissions'
import {
  getEmailIngestionStatus,
  listIngestions,
  pollEmailIngestion,
} from '../services/ingestionApi'
import './IngestionHistory.css'

const PAGE_SIZE = 20

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function sourceLabel(value) {
  return String(value || '').replaceAll('_', ' ')
}

export default function IngestionHistory() {
  const { can } = useAuth()
  const canPoll = can(Permission.DOCUMENTS_WRITE)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [sourceType, setSourceType] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [emailStatus, setEmailStatus] = useState(null)
  const [emailBusy, setEmailBusy] = useState(false)
  const [emailMessage, setEmailMessage] = useState('')

  const loadEmailStatus = useCallback(async () => {
    try {
      const data = await getEmailIngestionStatus()
      setEmailStatus(data)
    } catch {
      // Status panel is optional if the API is briefly unavailable.
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listIngestions({
        page,
        pageSize: PAGE_SIZE,
        sourceType: sourceType || undefined,
        status: status || undefined,
      })
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err.message || 'Failed to load ingestion history.')
    } finally {
      setLoading(false)
    }
  }, [page, sourceType, status])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    loadEmailStatus()
  }, [loadEmailStatus])

  const onPollEmail = async () => {
    if (!canPoll) return
    setEmailBusy(true)
    setEmailMessage('')
    setError('')
    try {
      const result = await pollEmailIngestion()
      setEmailMessage(result.message || `Poll finished (${result.status}).`)
      await loadEmailStatus()
      await load()
    } catch (err) {
      setError(err.message || 'Email poll failed.')
    } finally {
      setEmailBusy(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="ingestion-history">
      <header className="ingestion-history__header">
        <div>
          <h2>Ingestion History</h2>
          <p>Batch and email-attachment intake records (provider-independent foundation).</p>
        </div>
      </header>

      <section className="ingestion-history__email" aria-label="Email ingestion status">
        <div className="ingestion-history__email-grid">
          <div>
            <strong>Email provider</strong>
            <div>{emailStatus?.provider || '—'}</div>
          </div>
          <div>
            <strong>Configured</strong>
            <div>{emailStatus ? (emailStatus.configured ? 'Yes' : 'No') : '—'}</div>
          </div>
          <div>
            <strong>Last poll</strong>
            <div>{formatDate(emailStatus?.last_poll_at)}</div>
          </div>
          <div>
            <strong>Processed</strong>
            <div>{emailStatus?.processed_count ?? '—'}</div>
          </div>
          <div>
            <strong>Last error</strong>
            <div>{emailStatus?.last_error || '—'}</div>
          </div>
          <div>
            <strong>Worker mode</strong>
            <div>{emailStatus?.worker_mode || '—'}</div>
          </div>
        </div>
        {canPoll && (
          <button type="button" onClick={onPollEmail} disabled={emailBusy}>
            {emailBusy ? 'Polling…' : 'Poll Email'}
          </button>
        )}
        {emailMessage && <p className="ingestion-history__email-msg">{emailMessage}</p>}
      </section>

      <form
        className="ingestion-history__filters"
        onSubmit={(event) => {
          event.preventDefault()
          setPage(1)
          load()
        }}
      >
        <label>
          Source
          <select value={sourceType} onChange={(e) => { setSourceType(e.target.value); setPage(1) }}>
            <option value="">All</option>
            <option value="manual_upload">Manual upload</option>
            <option value="batch_upload">Batch upload</option>
            <option value="email_attachment">Email attachment</option>
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
            <option value="">All</option>
            <option value="queued">Queued</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="skipped">Skipped</option>
          </select>
        </label>
      </form>

      {error && <div className="ingestion-history__error">{error}</div>}

      {loading ? (
        <p>Loading…</p>
      ) : (
        <>
          <div className="ingestion-history__table-wrap">
            <table className="ingestion-history__table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Document</th>
                  <th>Job</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr>
                    <td colSpan={6}>No ingestion records yet.</td>
                  </tr>
                )}
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="ingestion-history__filename">{item.original_filename}</div>
                      {item.error_message && (
                        <small className="ingestion-history__err">{item.error_message}</small>
                      )}
                    </td>
                    <td>{sourceLabel(item.source_type)}</td>
                    <td>
                      <span className={`ingestion-history__status ingestion-history__status--${item.status}`}>
                        {item.status}
                      </span>
                    </td>
                    <td>
                      <code className="ingestion-history__code">
                        {item.document_id ? String(item.document_id).slice(0, 8) : '—'}
                      </code>
                    </td>
                    <td>
                      <code className="ingestion-history__code">
                        {item.processing_job_id ? String(item.processing_job_id).slice(0, 8) : '—'}
                      </code>
                    </td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ingestion-history__pager">
            <button type="button" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <span>
              Page {page} of {totalPages} ({total} total)
            </span>
            <button
              type="button"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
