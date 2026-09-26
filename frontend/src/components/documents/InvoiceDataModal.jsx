import './InvoiceDataModal.css'

function formatMoney(value, currency) {
  if (value === null || value === undefined) return '—'
  const amount = Number(value)
  const formatted = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
  return currency ? `${currency} ${formatted}` : formatted
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

function formatConfidence(value) {
  if (value === null || value === undefined) return '—'
  return `${Math.round(Number(value) * 100)}%`
}

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function InvoiceDataModal({ open, title, invoice, loading, error, onClose }) {
  if (!open) return null

  return (
    <div className="invoice-modal" role="presentation" onClick={onClose}>
      <div
        className="invoice-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="invoice-data-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="invoice-modal__header">
          <div>
            <p className="invoice-modal__eyebrow">Invoice data</p>
            <h2 id="invoice-data-title" className="invoice-modal__title">
              {title}
            </h2>
          </div>
          <button type="button" className="invoice-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="invoice-modal__body">
          {loading && <p className="invoice-modal__state">Loading invoice data…</p>}

          {!loading && error && (
            <p className="invoice-modal__state invoice-modal__state--error">{error}</p>
          )}

          {!loading && !error && !invoice && (
            <p className="invoice-modal__state">No invoice data is available yet.</p>
          )}

          {!loading && !error && invoice && (
            <dl className="invoice-modal__grid">
              <div>
                <dt>Vendor</dt>
                <dd>{displayValue(invoice.vendor_name)}</dd>
              </div>
              <div>
                <dt>Vendor ID</dt>
                <dd>{displayValue(invoice.vendor_id)}</dd>
              </div>
              <div>
                <dt>Invoice Number</dt>
                <dd>{displayValue(invoice.invoice_number)}</dd>
              </div>
              <div>
                <dt>Invoice Date</dt>
                <dd>{formatDate(invoice.invoice_date)}</dd>
              </div>
              <div>
                <dt>Subtotal</dt>
                <dd>{formatMoney(invoice.subtotal, invoice.currency)}</dd>
              </div>
              <div>
                <dt>Tax</dt>
                <dd>{formatMoney(invoice.tax_amount, invoice.currency)}</dd>
              </div>
              <div>
                <dt>Total</dt>
                <dd className="invoice-modal__total">
                  {formatMoney(invoice.total_amount, invoice.currency)}
                </dd>
              </div>
              <div>
                <dt>Currency</dt>
                <dd>{displayValue(invoice.currency)}</dd>
              </div>
              <div>
                <dt>Extraction Confidence</dt>
                <dd>{formatConfidence(invoice.extraction_confidence)}</dd>
              </div>
            </dl>
          )}
        </div>
      </div>
    </div>
  )
}

export default InvoiceDataModal
