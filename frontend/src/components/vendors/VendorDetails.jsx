import './VendorDetails.css'

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

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function VendorDetails({ open, vendor, loading, error, onClose }) {
  if (!open) return null

  return (
    <div className="vendor-details" role="presentation" onClick={onClose}>
      <div
        className="vendor-details__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="vendor-details-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="vendor-details__header">
          <div>
            <p className="vendor-details__eyebrow">Vendor details</p>
            <h2 id="vendor-details-title">{vendor?.name || 'Vendor'}</h2>
          </div>
          <button type="button" className="vendor-details__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="vendor-details__body">
          {loading && <p className="vendor-details__state">Loading vendor…</p>}
          {!loading && error && (
            <p className="vendor-details__state vendor-details__state--error">{error}</p>
          )}

          {!loading && !error && vendor && (
            <>
              <section>
                <h3>Vendor information</h3>
                <dl className="vendor-details__grid">
                  <div>
                    <dt>Name</dt>
                    <dd>{displayValue(vendor.name)}</dd>
                  </div>
                  <div>
                    <dt>Email</dt>
                    <dd>{displayValue(vendor.email)}</dd>
                  </div>
                  <div>
                    <dt>Phone</dt>
                    <dd>{displayValue(vendor.phone)}</dd>
                  </div>
                  <div>
                    <dt>Tax ID</dt>
                    <dd>{displayValue(vendor.tax_id)}</dd>
                  </div>
                  <div className="vendor-details__wide">
                    <dt>Address</dt>
                    <dd>{displayValue(vendor.address)}</dd>
                  </div>
                </dl>
              </section>

              <section>
                <h3>Summary</h3>
                <div className="vendor-details__summary">
                  <div>
                    <span>Total invoices</span>
                    <strong>{vendor.summary?.invoice_count ?? 0}</strong>
                  </div>
                  <div>
                    <span>Total purchase orders</span>
                    <strong>{vendor.summary?.purchase_order_count ?? 0}</strong>
                  </div>
                </div>
              </section>

              <section>
                <h3>Invoices</h3>
                {(!vendor.invoices || vendor.invoices.length === 0) && (
                  <p className="vendor-details__empty">No linked invoices.</p>
                )}
                {vendor.invoices?.length > 0 && (
                  <div className="vendor-details__table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Invoice number</th>
                          <th>Date</th>
                          <th>Total</th>
                          <th>Currency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {vendor.invoices.map((invoice) => (
                          <tr key={invoice.id}>
                            <td>{displayValue(invoice.invoice_number)}</td>
                            <td>{formatDate(invoice.invoice_date)}</td>
                            <td>{formatMoney(invoice.total_amount, invoice.currency)}</td>
                            <td>{displayValue(invoice.currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section>
                <h3>Purchase orders</h3>
                {(!vendor.purchase_orders || vendor.purchase_orders.length === 0) && (
                  <p className="vendor-details__empty">No linked purchase orders.</p>
                )}
                {vendor.purchase_orders?.length > 0 && (
                  <div className="vendor-details__table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>PO number</th>
                          <th>Date</th>
                          <th>Total</th>
                          <th>Currency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {vendor.purchase_orders.map((po) => (
                          <tr key={po.id}>
                            <td>{displayValue(po.po_number)}</td>
                            <td>{formatDate(po.po_date)}</td>
                            <td>{formatMoney(po.total_amount, po.currency)}</td>
                            <td>{displayValue(po.currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default VendorDetails
