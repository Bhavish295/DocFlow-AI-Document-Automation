import './PurchaseOrderDataModal.css'

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

function PurchaseOrderDataModal({ open, title, purchaseOrder, loading, error, onClose }) {
  if (!open) return null

  return (
    <div className="po-modal" role="presentation" onClick={onClose}>
      <div
        className="po-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="po-data-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="po-modal__header">
          <div>
            <p className="po-modal__eyebrow">Purchase order data</p>
            <h2 id="po-data-title" className="po-modal__title">
              {title}
            </h2>
          </div>
          <button type="button" className="po-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="po-modal__body">
          {loading && <p className="po-modal__state">Loading purchase order data…</p>}

          {!loading && error && (
            <p className="po-modal__state po-modal__state--error">{error}</p>
          )}

          {!loading && !error && !purchaseOrder && (
            <p className="po-modal__state">No purchase order data is available yet.</p>
          )}

          {!loading && !error && purchaseOrder && (
            <dl className="po-modal__grid">
              <div>
                <dt>Vendor</dt>
                <dd>{displayValue(purchaseOrder.vendor_name)}</dd>
              </div>
              <div>
                <dt>Vendor ID</dt>
                <dd>{displayValue(purchaseOrder.vendor_id)}</dd>
              </div>
              <div>
                <dt>PO Number</dt>
                <dd>{displayValue(purchaseOrder.po_number)}</dd>
              </div>
              <div>
                <dt>PO Date</dt>
                <dd>{formatDate(purchaseOrder.po_date)}</dd>
              </div>
              <div>
                <dt>Subtotal</dt>
                <dd>{formatMoney(purchaseOrder.subtotal, purchaseOrder.currency)}</dd>
              </div>
              <div>
                <dt>Tax</dt>
                <dd>{formatMoney(purchaseOrder.tax_amount, purchaseOrder.currency)}</dd>
              </div>
              <div>
                <dt>Total</dt>
                <dd className="po-modal__total">
                  {formatMoney(purchaseOrder.total_amount, purchaseOrder.currency)}
                </dd>
              </div>
              <div>
                <dt>Currency</dt>
                <dd>{displayValue(purchaseOrder.currency)}</dd>
              </div>
              <div>
                <dt>Extraction Confidence</dt>
                <dd>{formatConfidence(purchaseOrder.extraction_confidence)}</dd>
              </div>
            </dl>
          )}
        </div>
      </div>
    </div>
  )
}

export default PurchaseOrderDataModal
