import { useEffect, useState } from 'react'
import './VendorForm.css'

const EMPTY_FORM = {
  name: '',
  email: '',
  phone: '',
  address: '',
  tax_id: '',
}

function normalizeInitial(values) {
  if (!values) return {}
  return {
    name: values.name || '',
    email: values.email || '',
    phone: values.phone || '',
    address: values.address || '',
    tax_id: values.tax_id || '',
  }
}

function VendorForm({ open, mode, initialValues, submitting, error, onSubmit, onClose }) {
  const [form, setForm] = useState(() => ({ ...EMPTY_FORM, ...normalizeInitial(initialValues) }))

  useEffect(() => {
    setForm({ ...EMPTY_FORM, ...normalizeInitial(initialValues) })
  }, [initialValues, open])

  if (!open) return null

  const title = mode === 'edit' ? 'Edit vendor' : 'Add vendor'

  const handleChange = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    const name = form.name.trim()
    if (!name) return
    onSubmit({
      name,
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      address: form.address.trim() || null,
      tax_id: form.tax_id.trim() || null,
    })
  }

  return (
    <div className="vendor-form" role="presentation" onClick={onClose}>
      <div
        className="vendor-form__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="vendor-form-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="vendor-form__header">
          <div>
            <p className="vendor-form__eyebrow">Vendors</p>
            <h2 id="vendor-form-title">{title}</h2>
          </div>
          <button type="button" className="vendor-form__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <form className="vendor-form__body" onSubmit={handleSubmit}>
          <label>
            Vendor name
            <input
              required
              value={form.name}
              onChange={handleChange('name')}
              placeholder="ABC Traders"
              autoFocus
            />
          </label>
          <label>
            Email
            <input
              type="email"
              value={form.email}
              onChange={handleChange('email')}
              placeholder="ops@vendor.example"
            />
          </label>
          <label>
            Phone
            <input value={form.phone} onChange={handleChange('phone')} placeholder="03001234567" />
          </label>
          <label>
            Tax ID
            <input value={form.tax_id} onChange={handleChange('tax_id')} placeholder="TAX-100" />
          </label>
          <label>
            Address
            <textarea
              value={form.address}
              onChange={handleChange('address')}
              rows={3}
              placeholder="Street, city"
            />
          </label>

          {error && <p className="vendor-form__error">{error}</p>}

          <div className="vendor-form__actions">
            <button type="button" className="vendor-form__secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="vendor-form__primary" disabled={submitting || !form.name.trim()}>
              {submitting ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Create vendor'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default VendorForm
