import { useCallback, useEffect, useState } from 'react'
import { listAuditLogs } from '../services/auditLogsApi'
import './EntityList.css'

const PAGE_SIZE = 25

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value))
}

export default function AuditLogs() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listAuditLogs({
        page,
        pageSize: PAGE_SIZE,
        action: action || undefined,
        resourceType: resourceType || undefined,
      })
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err.message || 'Failed to load audit logs.')
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, action, resourceType])

  useEffect(() => {
    load()
  }, [load])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="entity-list">
      <header className="entity-list__intro">
        <div>
          <p className="entity-list__kicker">Security</p>
          <h2 className="entity-list__title">Audit logs</h2>
          <p className="entity-list__desc">
            Traceable history of authentication, document, review, workflow, and agent actions.
            Secrets are never stored in audit details.
          </p>
        </div>
      </header>

      <form
        className="entity-list__filters"
        onSubmit={(event) => {
          event.preventDefault()
          setPage(1)
          load()
        }}
      >
        <label>
          Action contains
          <input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="login_success"
          />
        </label>
        <label>
          Resource type
          <input
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value)}
            placeholder="document"
          />
        </label>
        <button type="submit">Apply</button>
      </form>

      {error && <div className="entity-list__error">{error}</div>}

      {loading ? (
        <p className="entity-list__muted">Loading audit logs…</p>
      ) : items.length === 0 ? (
        <div className="entity-list__empty">
          <h3>No audit events yet</h3>
          <p>Actions such as login, upload, review, and agent runs will appear here.</p>
        </div>
      ) : (
        <>
          <div className="entity-list__table-wrap">
            <table className="entity-list__table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Resource</th>
                  <th>Resource ID</th>
                  <th>User</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td className="entity-list__cell-muted">{formatDate(row.created_at)}</td>
                    <td className="entity-list__action-name">{row.action}</td>
                    <td>{row.resource_type || '—'}</td>
                    <td>
                      <code className="entity-list__code">
                        {row.resource_id ? String(row.resource_id).slice(0, 12) : '—'}
                      </code>
                    </td>
                    <td>
                      <code className="entity-list__code">
                        {row.user_id ? String(row.user_id).slice(0, 8) : '—'}
                      </code>
                    </td>
                    <td className="entity-list__details">{row.details || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="entity-list__pager">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <span>
              Page {page} of {totalPages} ({total} total)
            </span>
            <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
