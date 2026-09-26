import { useCallback, useEffect, useMemo, useState } from 'react'
import VendorDetails from '../components/vendors/VendorDetails'
import VendorForm from '../components/vendors/VendorForm'
import {
  createVendor,
  deleteVendor,
  getVendor,
  getVendors,
  updateVendor,
} from '../services/vendorsApi'
import './Vendors.css'

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
  }).format(new Date(value))
}

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function Vendors() {
  const [vendors, setVendors] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [formMode, setFormMode] = useState('create')
  const [formInitial, setFormInitial] = useState(null)
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState('')
  const [detailsVendor, setDetailsVendor] = useState(null)
  const [deletingId, setDeletingId] = useState(null)

  const loadVendors = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const payload = await getVendors({ page: 1, pageSize: 100 })
      setVendors(payload.items || [])
    } catch (err) {
      setError(err.message || 'Failed to load vendors.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadVendors()
  }, [loadVendors])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return vendors
    return vendors.filter((vendor) => {
      const haystack = [vendor.name, vendor.email, vendor.phone, vendor.tax_id]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return haystack.includes(query)
    })
  }, [vendors, search])

  const openCreate = () => {
    setFormMode('create')
    setFormInitial(null)
    setEditingId(null)
    setFormError('')
    setFormOpen(true)
  }

  const openEdit = (vendor) => {
    setFormMode('edit')
    setFormInitial(vendor)
    setEditingId(vendor.id)
    setFormError('')
    setFormOpen(true)
  }

  const onSubmitForm = async (data) => {
    setFormSubmitting(true)
    setFormError('')
    setSuccess('')
    try {
      if (formMode === 'edit' && editingId) {
        await updateVendor(editingId, data)
        setSuccess(`Updated “${data.name}”.`)
      } else {
        await createVendor(data)
        setSuccess(`Created “${data.name}”.`)
      }
      setFormOpen(false)
      await loadVendors()
    } catch (err) {
      setFormError(err.message || 'Unable to save vendor.')
    } finally {
      setFormSubmitting(false)
    }
  }

  const onView = async (vendor) => {
    setDetailsOpen(true)
    setDetailsLoading(true)
    setDetailsError('')
    setDetailsVendor(null)
    try {
      const payload = await getVendor(vendor.id)
      setDetailsVendor(payload)
    } catch (err) {
      setDetailsError(err.message || 'Failed to load vendor details.')
    } finally {
      setDetailsLoading(false)
    }
  }

  const onDelete = async (vendor) => {
    const confirmed = window.confirm(`Delete vendor “${vendor.name}”?`)
    if (!confirmed) return

    setDeletingId(vendor.id)
    setError('')
    setSuccess('')
    try {
      await deleteVendor(vendor.id)
      setSuccess(`Deleted “${vendor.name}”.`)
      await loadVendors()
    } catch (err) {
      setError(err.message || 'Failed to delete vendor.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="vendors-page">
      <section className="vendors-page__intro">
        <div>
          <p className="vendors-page__kicker">Directory</p>
          <h2 className="vendors-page__title">Vendors</h2>
          <p className="vendors-page__desc">
            Maintain normalized vendor records linked from invoice and purchase order extraction.
          </p>
        </div>
        <button type="button" className="vendors-page__primary" onClick={openCreate}>
          Add vendor
        </button>
      </section>

      <section className="vendors-page__toolbar">
        <label className="vendors-page__search">
          <span>Search</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name, email, phone, tax ID"
          />
        </label>
      </section>

      {error && <div className="vendors-page__alert vendors-page__alert--error">{error}</div>}
      {success && <div className="vendors-page__alert vendors-page__alert--success">{success}</div>}

      <section className="vendors-page__list" aria-label="Vendors">
        <div className="vendors-page__list-header">
          <h3>Vendor list</h3>
          <p>
            {loading
              ? 'Loading…'
              : `${filtered.length} vendor${filtered.length === 1 ? '' : 's'}`}
          </p>
        </div>

        {loading && <div className="vendors-page__state">Loading vendors…</div>}

        {!loading && filtered.length === 0 && (
          <div className="vendors-page__state">
            {vendors.length === 0
              ? 'No vendors yet. Extract invoice/PO data or add a vendor manually.'
              : 'No vendors match your search.'}
          </div>
        )}

        {!loading && filtered.length > 0 && (
          <>
            <div className="vendors-page__table-wrap">
              <table className="vendors-page__table">
                <thead>
                  <tr>
                    <th>Vendor name</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Tax ID</th>
                    <th>Invoices</th>
                    <th>Purchase orders</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((vendor) => (
                    <tr key={vendor.id}>
                      <td>{vendor.name}</td>
                      <td>{displayValue(vendor.email)}</td>
                      <td>{displayValue(vendor.phone)}</td>
                      <td>{displayValue(vendor.tax_id)}</td>
                      <td>{vendor.invoice_count}</td>
                      <td>{vendor.purchase_order_count}</td>
                      <td>{formatDate(vendor.created_at)}</td>
                      <td>
                        <div className="vendors-page__actions">
                          <button type="button" onClick={() => onView(vendor)}>
                            View
                          </button>
                          <button type="button" onClick={() => openEdit(vendor)}>
                            Edit
                          </button>
                          <button
                            type="button"
                            className="vendors-page__danger"
                            onClick={() => onDelete(vendor)}
                            disabled={deletingId === vendor.id}
                          >
                            {deletingId === vendor.id ? 'Deleting…' : 'Delete'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="vendors-page__cards">
              {filtered.map((vendor) => (
                <li key={vendor.id} className="vendors-page__card">
                  <div className="vendors-page__card-top">
                    <div>
                      <p className="vendors-page__card-title">{vendor.name}</p>
                      <p className="vendors-page__card-meta">{displayValue(vendor.email)}</p>
                    </div>
                    <p className="vendors-page__card-date">{formatDate(vendor.created_at)}</p>
                  </div>
                  <dl className="vendors-page__meta">
                    <div>
                      <dt>Phone</dt>
                      <dd>{displayValue(vendor.phone)}</dd>
                    </div>
                    <div>
                      <dt>Tax ID</dt>
                      <dd>{displayValue(vendor.tax_id)}</dd>
                    </div>
                    <div>
                      <dt>Invoices</dt>
                      <dd>{vendor.invoice_count}</dd>
                    </div>
                    <div>
                      <dt>POs</dt>
                      <dd>{vendor.purchase_order_count}</dd>
                    </div>
                  </dl>
                  <div className="vendors-page__actions">
                    <button type="button" onClick={() => onView(vendor)}>
                      View
                    </button>
                    <button type="button" onClick={() => openEdit(vendor)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="vendors-page__danger"
                      onClick={() => onDelete(vendor)}
                      disabled={deletingId === vendor.id}
                    >
                      {deletingId === vendor.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <VendorForm
        open={formOpen}
        mode={formMode}
        initialValues={formInitial}
        submitting={formSubmitting}
        error={formError}
        onSubmit={onSubmitForm}
        onClose={() => setFormOpen(false)}
      />

      <VendorDetails
        open={detailsOpen}
        vendor={detailsVendor}
        loading={detailsLoading}
        error={detailsError}
        onClose={() => setDetailsOpen(false)}
      />
    </div>
  )
}

export default Vendors
