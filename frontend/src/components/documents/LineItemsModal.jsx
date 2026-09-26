import './LineItemsModal.css'

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '—'
  return Number(value)
}

function LineItemsModal({ open, title, items, loading, error, onClose }) {
  if (!open) return null

  return (
    <div className="line-items-modal" role="presentation" onClick={onClose}>
      <div
        className="line-items-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="line-items-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="line-items-modal__header">
          <div>
            <p className="line-items-modal__eyebrow">Line items</p>
            <h2 id="line-items-title">{title || 'Document'}</h2>
          </div>
          <button type="button" className="line-items-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="line-items-modal__body">
          {loading && <p className="line-items-modal__state">Loading line items…</p>}
          {!loading && error && (
            <p className="line-items-modal__state line-items-modal__state--error">{error}</p>
          )}
          {!loading && !error && (!items || items.length === 0) && (
            <p className="line-items-modal__state">No line items extracted for this document.</p>
          )}
          {!loading && !error && items?.length > 0 && (
            <div className="line-items-modal__table-wrap">
              <table className="line-items-modal__table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item / Description</th>
                    <th>Code</th>
                    <th>Quantity</th>
                    <th>Unit</th>
                    <th>Unit Price</th>
                    <th>Line Total</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.line_number}</td>
                      <td>{displayValue(item.description)}</td>
                      <td>{displayValue(item.item_code)}</td>
                      <td>{formatNumber(item.quantity)}</td>
                      <td>{displayValue(item.unit)}</td>
                      <td>{formatNumber(item.unit_price)}</td>
                      <td>{formatNumber(item.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default LineItemsModal
