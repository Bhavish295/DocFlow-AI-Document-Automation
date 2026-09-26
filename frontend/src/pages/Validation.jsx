import { useCallback, useEffect, useMemo, useState } from 'react'
import { listDocuments } from '../services/documentsApi'
import {
  createValidation,
  listThreeWayMatches,
  listValidations,
  runThreeWayMatch,
} from '../services/validationsApi'
import './Validation.css'

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function matchLabel(value) {
  if (value === true) return 'Match'
  if (value === false) return 'Mismatch'
  return 'Review'
}

function statusLabel(value) {
  if (!value) return '—'
  return String(value).replaceAll('_', ' ')
}

function dimensionLabel(name) {
  const labels = {
    vendor: 'Vendor',
    po_reference: 'PO Reference',
    grn_reference: 'GRN Reference',
    quantity: 'Quantity',
    financial: 'Financial Validation',
    relationships: 'Relationships',
  }
  return labels[name] || statusLabel(name)
}

function Validation() {
  const [validations, setValidations] = useState([])
  const [threeWayMatches, setThreeWayMatches] = useState([])
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [threeWaySubmitting, setThreeWaySubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [invoiceId, setInvoiceId] = useState('')
  const [purchaseOrderId, setPurchaseOrderId] = useState('')
  const [threeWayInvoiceDocId, setThreeWayInvoiceDocId] = useState('')
  const [threeWayPoDocId, setThreeWayPoDocId] = useState('')
  const [threeWayGrnDocId, setThreeWayGrnDocId] = useState('')
  const [latestThreeWay, setLatestThreeWay] = useState(null)

  const invoiceOptions = useMemo(
    () => documents.filter((doc) => doc.has_invoice && doc.invoice_id),
    [documents],
  )
  const poOptions = useMemo(
    () => documents.filter((doc) => doc.has_purchase_order && doc.purchase_order_id),
    [documents],
  )
  const threeWayInvoiceOptions = useMemo(
    () => documents.filter((doc) => doc.document_type === 'invoice' && doc.has_invoice),
    [documents],
  )
  const threeWayPoOptions = useMemo(
    () => documents.filter((doc) => doc.document_type === 'purchase_order' && doc.has_purchase_order),
    [documents],
  )
  const threeWayGrnOptions = useMemo(
    () => documents.filter((doc) => doc.document_type === 'goods_receipt' && doc.has_goods_receipt),
    [documents],
  )

  const loadPage = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [validationData, threeWayData, documentData] = await Promise.all([
        listValidations({ page: 1, pageSize: 50 }),
        listThreeWayMatches({ page: 1, pageSize: 50 }),
        listDocuments({ page: 1, pageSize: 100 }),
      ])
      setValidations(validationData.items)
      setThreeWayMatches(threeWayData.items)
      setDocuments(documentData.items)
    } catch (err) {
      setError(err.message || 'Failed to load validations.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadPage()
  }, [loadPage])

  const onValidate = async (event) => {
    event.preventDefault()
    if (!invoiceId || !purchaseOrderId) {
      setError('Select both an invoice and a purchase order.')
      return
    }

    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const result = await createValidation(invoiceId, purchaseOrderId)
      setSuccess(`Validation completed with status “${result.status.replaceAll('_', ' ')}”.`)
      await loadPage()
    } catch (err) {
      setError(err.message || 'Validation failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const onThreeWayMatch = async (event) => {
    event.preventDefault()
    if (!threeWayInvoiceDocId || !threeWayPoDocId || !threeWayGrnDocId) {
      setError('Select invoice, purchase order, and goods receipt documents.')
      return
    }

    setThreeWaySubmitting(true)
    setError('')
    setSuccess('')
    try {
      const result = await runThreeWayMatch({
        invoice_document_id: threeWayInvoiceDocId,
        purchase_order_document_id: threeWayPoDocId,
        goods_receipt_document_id: threeWayGrnDocId,
      })
      setLatestThreeWay(result)
      setSuccess(`3-way match completed with status “${result.status.replaceAll('_', ' ')}”.`)
      await loadPage()
    } catch (err) {
      setError(err.message || '3-way matching failed.')
    } finally {
      setThreeWaySubmitting(false)
    }
  }

  return (
    <div className="validation-page">
      <section className="validation-page__intro">
        <p className="validation-page__kicker">Controls</p>
        <h2 className="validation-page__title">Validation</h2>
        <p className="validation-page__desc">
          Compare extracted invoice fields against purchase order data, and run deterministic
          3-way matching with goods receipts. Results are assistive only — they never approve,
          reject, or block payment.
        </p>
      </section>

      <section className="validation-page__create">
        <h3>Run Invoice ↔ PO validation</h3>
        <form className="validation-page__form" onSubmit={onValidate}>
          <label>
            Invoice
            <select
              value={invoiceId}
              onChange={(event) => setInvoiceId(event.target.value)}
              disabled={submitting}
            >
              <option value="">Select invoice</option>
              {invoiceOptions.map((doc) => (
                <option key={doc.invoice_id} value={doc.invoice_id}>
                  {doc.original_filename}
                </option>
              ))}
            </select>
          </label>
          <label>
            Purchase Order
            <select
              value={purchaseOrderId}
              onChange={(event) => setPurchaseOrderId(event.target.value)}
              disabled={submitting}
            >
              <option value="">Select purchase order</option>
              {poOptions.map((doc) => (
                <option key={doc.purchase_order_id} value={doc.purchase_order_id}>
                  {doc.original_filename}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? 'Validating…' : 'Validate'}
          </button>
        </form>
        {invoiceOptions.length === 0 || poOptions.length === 0 ? (
          <p className="validation-page__hint">
            Process at least one invoice and one purchase order on the Documents page first.
          </p>
        ) : null}
      </section>

      <section className="validation-page__create">
        <h3>3-Way Matching</h3>
        <p className="validation-page__hint">
          Invoice ↔ Purchase Order ↔ Goods Receipt. Quantity line items are not fully modeled yet,
          so quantity is reported as not evaluable.
        </p>
        <form className="validation-page__form validation-page__form--three-way" onSubmit={onThreeWayMatch}>
          <label>
            Invoice
            <select
              value={threeWayInvoiceDocId}
              onChange={(event) => setThreeWayInvoiceDocId(event.target.value)}
              disabled={threeWaySubmitting}
            >
              <option value="">Select invoice document</option>
              {threeWayInvoiceOptions.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.original_filename}
                </option>
              ))}
            </select>
          </label>
          <label>
            Purchase Order
            <select
              value={threeWayPoDocId}
              onChange={(event) => setThreeWayPoDocId(event.target.value)}
              disabled={threeWaySubmitting}
            >
              <option value="">Select purchase order document</option>
              {threeWayPoOptions.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.original_filename}
                </option>
              ))}
            </select>
          </label>
          <label>
            Goods Receipt
            <select
              value={threeWayGrnDocId}
              onChange={(event) => setThreeWayGrnDocId(event.target.value)}
              disabled={threeWaySubmitting}
            >
              <option value="">Select goods receipt document</option>
              {threeWayGrnOptions.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.original_filename}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={threeWaySubmitting}>
            {threeWaySubmitting ? 'Matching…' : 'Run 3-Way Match'}
          </button>
        </form>

        {latestThreeWay && (
          <div className="validation-page__three-way-result">
            <div className="validation-page__card-top">
              <div>
                <p className="validation-page__card-title">Latest 3-way result</p>
                <p className="validation-page__card-vendor">
                  {latestThreeWay.invoice?.number || 'Invoice'} ·{' '}
                  {latestThreeWay.purchase_order?.number || 'PO'} ·{' '}
                  {latestThreeWay.goods_receipt?.number || 'GRN'}
                </p>
              </div>
              <span className={`validation-page__status validation-page__status--${latestThreeWay.status}`}>
                {statusLabel(latestThreeWay.status)}
              </span>
            </div>
            {latestThreeWay.overall_confidence != null && (
              <p className="validation-page__hint">
                Confidence: {Math.round(Number(latestThreeWay.overall_confidence) * 100)}% (assistive only)
              </p>
            )}
            <dl className="validation-page__meta">
              {latestThreeWay.dimensions?.map((dimension) => (
                <div key={dimension.name}>
                  <dt>{dimensionLabel(dimension.name)}</dt>
                  <dd>
                    <span className={`validation-page__status validation-page__status--${dimension.status}`}>
                      {statusLabel(dimension.status)}
                    </span>
                    {dimension.detail ? <span className="validation-page__dim-detail">{dimension.detail}</span> : null}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="validation-page__evidence">
              <div>
                <h4>Matched Fields</h4>
                <ul>
                  {(latestThreeWay.matched_fields || []).length === 0 && <li>—</li>}
                  {(latestThreeWay.matched_fields || []).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Mismatched Fields</h4>
                <ul>
                  {(latestThreeWay.mismatched_fields || []).length === 0 && <li>—</li>}
                  {(latestThreeWay.mismatched_fields || []).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Missing / Not Evaluated</h4>
                <ul>
                  {(latestThreeWay.missing_fields || []).length === 0 && <li>—</li>}
                  {(latestThreeWay.missing_fields || []).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
            {(latestThreeWay.quantity_evidence || []).length > 0 && (
              <div className="validation-page__qty-table-wrap">
                <h4>Quantity line evidence</h4>
                <table className="validation-page__qty-table">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>PO</th>
                      <th>GRN</th>
                      <th>Invoice</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latestThreeWay.quantity_evidence.map((item) => (
                      <tr key={item.item_key}>
                        <td>{item.item_code || item.description || item.item_key}</td>
                        <td>{item.po_quantity ?? '—'}</td>
                        <td>{item.grn_quantity ?? '—'}</td>
                        <td>{item.invoice_quantity ?? '—'}</td>
                        <td>
                          <span className={`validation-page__status validation-page__status--${item.status}`}>
                            {statusLabel(item.status)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <pre className="validation-page__explanation">{latestThreeWay.explanation}</pre>
          </div>
        )}
      </section>

      {error && <div className="validation-page__alert validation-page__alert--error">{error}</div>}
      {success && <div className="validation-page__alert validation-page__alert--success">{success}</div>}

      <section className="validation-page__list" aria-label="Validation results">
        <div className="validation-page__list-header">
          <h3>Invoice ↔ PO Results</h3>
          <p>{loading ? 'Loading…' : `${validations.length} record${validations.length === 1 ? '' : 's'}`}</p>
        </div>

        {loading && <div className="validation-page__state">Loading validations…</div>}

        {!loading && validations.length === 0 && (
          <div className="validation-page__state">
            No validations yet. Run a comparison above to get started.
          </div>
        )}

        {!loading && validations.length > 0 && (
          <>
            <div className="validation-page__table-wrap">
              <table className="validation-page__table">
                <thead>
                  <tr>
                    <th>Invoice Number</th>
                    <th>PO Number</th>
                    <th>Vendor</th>
                    <th>Status</th>
                    <th>Vendor Match</th>
                    <th>Currency Match</th>
                    <th>Subtotal Match</th>
                    <th>Tax Match</th>
                    <th>Total Match</th>
                    <th>Mismatch Summary</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {validations.map((item) => (
                    <tr key={item.id}>
                      <td>{item.invoice_number || '—'}</td>
                      <td>{item.po_number || '—'}</td>
                      <td>{item.vendor_name || '—'}</td>
                      <td>
                        <span className={`validation-page__status validation-page__status--${item.status}`}>
                          {item.status.replaceAll('_', ' ')}
                        </span>
                      </td>
                      <td>{matchLabel(item.vendor_match)}</td>
                      <td>{matchLabel(item.currency_match)}</td>
                      <td>{matchLabel(item.subtotal_match)}</td>
                      <td>{matchLabel(item.tax_match)}</td>
                      <td>{matchLabel(item.total_match)}</td>
                      <td className="validation-page__summary">{item.mismatch_summary || '—'}</td>
                      <td>{formatDate(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="validation-page__cards">
              {validations.map((item) => (
                <li key={item.id} className="validation-page__card">
                  <div className="validation-page__card-top">
                    <div>
                      <p className="validation-page__card-title">
                        {item.invoice_number || 'Invoice'} ↔ {item.po_number || 'PO'}
                      </p>
                      <p className="validation-page__card-vendor">{item.vendor_name || 'Vendor unavailable'}</p>
                    </div>
                    <span className={`validation-page__status validation-page__status--${item.status}`}>
                      {item.status.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <dl className="validation-page__meta">
                    <div>
                      <dt>Vendor</dt>
                      <dd>{matchLabel(item.vendor_match)}</dd>
                    </div>
                    <div>
                      <dt>Currency</dt>
                      <dd>{matchLabel(item.currency_match)}</dd>
                    </div>
                    <div>
                      <dt>Subtotal</dt>
                      <dd>{matchLabel(item.subtotal_match)}</dd>
                    </div>
                    <div>
                      <dt>Tax</dt>
                      <dd>{matchLabel(item.tax_match)}</dd>
                    </div>
                    <div>
                      <dt>Total</dt>
                      <dd>{matchLabel(item.total_match)}</dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDate(item.created_at)}</dd>
                    </div>
                  </dl>
                  <p className="validation-page__summary">{item.mismatch_summary || 'No mismatches reported.'}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="validation-page__list" aria-label="Three-way match results">
        <div className="validation-page__list-header">
          <h3>3-Way Match History</h3>
          <p>
            {loading
              ? 'Loading…'
              : `${threeWayMatches.length} record${threeWayMatches.length === 1 ? '' : 's'}`}
          </p>
        </div>
        {!loading && threeWayMatches.length === 0 && (
          <div className="validation-page__state">No 3-way matches yet.</div>
        )}
        {!loading && threeWayMatches.length > 0 && (
          <ul className="validation-page__cards">
            {threeWayMatches.map((item) => (
              <li key={item.id} className="validation-page__card">
                <div className="validation-page__card-top">
                  <div>
                    <p className="validation-page__card-title">
                      {(item.invoice && item.invoice.number) || 'Invoice'} ↔{' '}
                      {(item.purchase_order && item.purchase_order.number) || 'PO'} ↔{' '}
                      {(item.goods_receipt && item.goods_receipt.number) || 'GRN'}
                    </p>
                    <p className="validation-page__card-vendor">
                      {(item.invoice && item.invoice.filename) || 'Invoice doc'}
                    </p>
                  </div>
                  <span className={`validation-page__status validation-page__status--${item.status}`}>
                    {statusLabel(item.status)}
                  </span>
                </div>
                <dl className="validation-page__meta">
                  <div>
                    <dt>Vendor</dt>
                    <dd>{statusLabel(item.vendor_status)}</dd>
                  </div>
                  <div>
                    <dt>PO Ref</dt>
                    <dd>{statusLabel(item.po_reference_status)}</dd>
                  </div>
                  <div>
                    <dt>GRN Ref</dt>
                    <dd>{statusLabel(item.grn_reference_status)}</dd>
                  </div>
                  <div>
                    <dt>Quantity</dt>
                    <dd>{statusLabel(item.quantity_status)}</dd>
                  </div>
                  <div>
                    <dt>Financial</dt>
                    <dd>{statusLabel(item.financial_status)}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>{formatDate(item.created_at)}</dd>
                  </div>
                </dl>
                <p className="validation-page__summary">
                  {(item.mismatched_fields && item.mismatched_fields[0])
                    || (item.missing_fields && item.missing_fields[0])
                    || 'No issues listed.'}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

export default Validation
