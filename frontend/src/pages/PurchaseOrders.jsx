import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import PurchaseOrderDataModal from '../components/documents/PurchaseOrderDataModal'
import { getDocumentPurchaseOrder, listDocuments } from '../services/documentsApi'
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

export default function PurchaseOrders() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [purchaseOrder, setPurchaseOrder] = useState(null)
  const [modalLoading, setModalLoading] = useState(false)
  const [modalError, setModalError] = useState('')
  const [modalTitle, setModalTitle] = useState('Purchase order')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listDocuments({
        page,
        pageSize: PAGE_SIZE,
        documentType: 'purchase_order',
        status: status || undefined,
        search: search || undefined,
      })
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err.message || 'Failed to load purchase orders.')
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, status, search])

  useEffect(() => {
    load()
  }, [load])

  const openPo = async (doc) => {
    setModalOpen(true)
    setModalTitle(doc.original_filename || 'Purchase order')
    setPurchaseOrder(null)
    setModalError('')
    setModalLoading(true)
    try {
      const payload = await getDocumentPurchaseOrder(doc.id)
      setPurchaseOrder(payload)
    } catch (err) {
      setModalError(err.message || 'PO data is not available yet. Extract PO fields from Documents first.')
    } finally {
      setModalLoading(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="entity-list">
      <header className="entity-list__intro">
        <div>
          <p className="entity-list__kicker">Purchase orders</p>
          <h2 className="entity-list__title">PO matching view</h2>
          <p className="entity-list__desc">
            Purchase order documents with extraction status and links into validation and review.
          </p>
        </div>
        <Link className="entity-list__link" to="/validation">
          Open Validation
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
        <p className="entity-list__muted">Loading purchase orders…</p>
      ) : items.length === 0 ? (
        <div className="entity-list__empty">
          <h3>No purchase orders yet</h3>
          <p>Upload PO documents and run extraction from the Documents page.</p>
          <Link to="/documents">Go to Documents</Link>
        </div>
      ) : (
        <>
          <div className="entity-list__table-wrap">
            <table className="entity-list__table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Vendor</th>
                  <th>Extracted</th>
                  <th>Review</th>
                  <th>Uploaded</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <span className="entity-list__filename">{doc.original_filename}</span>
                    </td>
                    <td>
                      <span className={`status-badge status-badge--${doc.status || 'uploaded'}`}>
                        {statusLabel(doc.status)}
                      </span>
                    </td>
                    <td>{doc.vendor_name || '—'}</td>
                    <td>{doc.has_purchase_order ? 'Yes' : 'No'}</td>
                    <td>
                      {doc.requires_review ? (
                        <span className="status-badge status-badge--needs_review">Review required</span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="entity-list__cell-muted">{formatDate(doc.uploaded_at)}</td>
                    <td>
                      <div className="entity-list__actions">
                        <button
                          type="button"
                          onClick={() => openPo(doc)}
                          disabled={!doc.has_purchase_order}
                        >
                          View data
                        </button>
                      </div>
                    </td>
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

      <PurchaseOrderDataModal
        open={modalOpen}
        title={modalTitle}
        purchaseOrder={purchaseOrder}
        loading={modalLoading}
        error={modalError}
        onClose={() => setModalOpen(false)}
      />
    </div>
  )
}
