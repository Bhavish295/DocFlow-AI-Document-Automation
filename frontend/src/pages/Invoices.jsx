import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import InvoiceDataModal from '../components/documents/InvoiceDataModal'
import { getDocumentInvoice, listDocuments } from '../services/documentsApi'
import './EntityList.css'

const PAGE_SIZE = 20

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function statusLabel(value) {
  return String(value || '—').replaceAll('_', ' ')
}

export default function Invoices() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [invoice, setInvoice] = useState(null)
  const [modalLoading, setModalLoading] = useState(false)
  const [modalError, setModalError] = useState('')
  const [modalTitle, setModalTitle] = useState('Invoice')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listDocuments({
        page,
        pageSize: PAGE_SIZE,
        documentType: 'invoice',
        status: status || undefined,
        search: search || undefined,
      })
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err.message || 'Failed to load invoices.')
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, status, search])

  useEffect(() => {
    load()
  }, [load])

  const openInvoice = async (doc) => {
    setModalOpen(true)
    setModalTitle(doc.original_filename || 'Invoice')
    setInvoice(null)
    setModalError('')
    setModalLoading(true)
    try {
      const payload = await getDocumentInvoice(doc.id)
      setInvoice(payload)
    } catch (err) {
      setModalError(err.message || 'Invoice data is not available yet. Extract invoice fields from Documents first.')
    } finally {
      setModalLoading(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="entity-list">
      <header className="entity-list__intro">
        <div>
          <p className="entity-list__kicker">Invoices</p>
          <h2 className="entity-list__title">Invoice intake</h2>
          <p className="entity-list__desc">
            Documents classified as invoices with extraction status, vendor linkage, and review flags.
          </p>
        </div>
        <Link className="entity-list__link" to="/documents">
          Open Documents
        </Link>
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
          Search
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filename or text"
          />
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All</option>
            <option value="uploaded">Uploaded</option>
            <option value="processing">Processing</option>
            <option value="processed">Processed</option>
            <option value="failed">Failed</option>
            <option value="manual_review">Manual review</option>
          </select>
        </label>
        <button type="submit">Apply</button>
      </form>

      {error && <div className="entity-list__error">{error}</div>}

      {loading ? (
        <p className="entity-list__muted">Loading invoices…</p>
      ) : items.length === 0 ? (
        <div className="entity-list__empty">
          <h3>No invoices yet</h3>
          <p>Upload and process invoice documents, then extract invoice fields from the Documents page.</p>
          <Link to="/documents">Go to Documents</Link>
        </div>
      ) : (
        <>
          <table className="entity-list__table">
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>Vendor</th>
                <th>Extracted</th>
                <th>Review</th>
                <th>Uploaded</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.original_filename}</td>
                  <td>{statusLabel(doc.status)}</td>
                  <td>{doc.vendor_name || '—'}</td>
                  <td>{doc.has_invoice ? 'Yes' : 'No'}</td>
                  <td>{doc.requires_review ? 'Yes' : 'No'}</td>
                  <td>{formatDate(doc.uploaded_at)}</td>
                  <td>
                    <button type="button" onClick={() => openInvoice(doc)} disabled={!doc.has_invoice}>
                      View data
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

      <InvoiceDataModal
        open={modalOpen}
        title={modalTitle}
        invoice={invoice}
        loading={modalLoading}
        error={modalError}
        onClose={() => setModalOpen(false)}
      />
    </div>
  )
}
