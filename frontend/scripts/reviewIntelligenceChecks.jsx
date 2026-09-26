import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ReviewDetailsModal from '../src/components/reviews/ReviewDetailsModal.jsx'
import {
  REASON_EXPLANATIONS,
  formatConfidence,
  issueLabel,
} from '../src/components/reviews/fieldIntelligencePresentation.js'

const failures = []

function check(name, condition) {
  if (!condition) failures.push(name)
}

function renderModal(review, intelligenceState) {
  return renderToStaticMarkup(
    React.createElement(ReviewDetailsModal, {
      open: true,
      review,
      loading: false,
      error: '',
      submitting: false,
      onClose() {},
      onStart() {},
      onApprove() {},
      onReject() {},
      intelligenceState,
    }),
  )
}

const documentBase = {
  id: 'doc-1',
  original_filename: 'invoice.pdf',
  document_type: 'invoice',
  status: 'processed',
  uploaded_at: '2026-09-15T09:00:00Z',
}

function review(overrides = {}) {
  return {
    id: 'review-1',
    status: 'pending',
    priority: 'medium',
    reason: 'financial_consistency_mismatch',
    details: 'Field intelligence found actionable issues.',
    reviewer_notes: null,
    created_at: '2026-09-15T09:05:00Z',
    updated_at: '2026-09-15T09:05:00Z',
    document: documentBase,
    invoice: {
      invoice_number: 'INV-1827',
      invoice_date: '2026-09-10',
      vendor_name: 'ABC Pvt Ltd',
      subtotal: 450000,
      tax_amount: 81000,
      total_amount: 531000,
      currency: 'PKR',
    },
    purchase_order: null,
    validation: null,
    ...overrides,
  }
}

const invoiceReport = {
  document_id: 'doc-1',
  document_type: 'invoice',
  overall_status: 'needs_review',
  overall_confidence: 0.86,
  review_required: true,
  issues: ['subtotal_tax_total_mismatch'],
  fields: [
    {
      field_name: 'invoice_number',
      value: 'INV-1827',
      status: 'valid',
      confidence: 1,
      issues: [],
    },
    {
      field_name: 'tax_amount',
      value: 81000,
      status: 'suspicious',
      confidence: 0.45,
      issues: ['subtotal_tax_total_mismatch'],
    },
    {
      field_name: 'vendor_name',
      value: null,
      status: 'missing',
      confidence: 0,
      issues: ['missing'],
    },
    {
      field_name: 'invoice_date',
      value: '31-02-2026',
      status: 'invalid',
      confidence: 0.2,
      issues: ['invalid_date'],
    },
  ],
}

const ready = { status: 'ready', report: invoiceReport, error: '' }

const openHtml = renderModal(review({ reason: 'processing_failed', document: { ...documentBase, document_type: 'other' }, invoice: null }))
check('1 review details open', openHtml.includes('invoice.pdf') && openHtml.includes('Review details'))
check('1 no undefined null none', !/\b(undefined|null|None)\b/.test(openHtml))

const invoiceHtml = renderModal(review(), ready)
check('2 invoice field intelligence', invoiceHtml.includes('Field Intelligence') && invoiceHtml.includes('Invoice Number') && invoiceHtml.includes('INV-1827'))
check('2 keeps invoice data', invoiceHtml.includes('Invoice data') && invoiceHtml.includes('ABC Pvt Ltd'))

const poHtml = renderModal(
  review({
    reason: 'field_missing',
    document: { ...documentBase, original_filename: 'po.pdf', document_type: 'purchase_order' },
    invoice: null,
    purchase_order: { po_number: 'PO-7788', vendor_name: 'Northwind', subtotal: 10, tax_amount: 1, total_amount: 11, currency: 'USD' },
  }),
  {
    status: 'ready',
    error: '',
    report: {
      document_type: 'purchase_order',
      overall_status: 'valid',
      overall_confidence: 1,
      review_required: false,
      issues: [],
      fields: [
        { field_name: 'po_number', value: 'PO-7788', status: 'valid', confidence: 1, issues: [] },
      ],
    },
  },
)
check('3 po field intelligence', poHtml.includes('PO Number') && poHtml.includes('PO-7788') && poHtml.includes('Purchase order data'))

check('4 missing field', invoiceHtml.includes('Missing') && invoiceHtml.includes('>Missing<'))
check('5 suspicious field', invoiceHtml.includes('Suspicious') && invoiceHtml.includes(issueLabel('subtotal_tax_total_mismatch')))
check('6 invalid field', invoiceHtml.includes('Invalid') && invoiceHtml.includes('31-02-2026'))
check('7 confidence', invoiceHtml.includes(formatConfidence(0.86)) && invoiceHtml.includes(formatConfidence(0.45)) && invoiceHtml.includes('86%') && invoiceHtml.includes('45%'))
check('8 reason explanation', invoiceHtml.includes(REASON_EXPLANATIONS.financial_consistency_mismatch))
check('9 review actions', invoiceHtml.includes('Start Review') && invoiceHtml.includes('Approve') && invoiceHtml.includes('Reject'))

const older = renderModal(review({
  reason: 'processing_failed',
  document: { ...documentBase, document_type: 'other' },
  invoice: null,
}))
check('10 older review renders', older.includes(REASON_EXPLANATIONS.processing_failed) && older.includes('Start Review') && !older.includes('Invoice Number'))
check('10 other hides field table', !older.includes('Field Intelligence'))

const failed = renderModal(review(), {
  status: 'error',
  report: null,
  error: 'Field intelligence could not be loaded.',
})
check('11 intelligence failure keeps review', failed.includes('Field intelligence could not be loaded.') && failed.includes('invoice.pdf') && failed.includes('Approve') && failed.includes('Invoice data'))

const missingData = renderModal(review({ invoice: null }), {
  status: 'ready',
  error: '',
  report: {
    document_type: 'invoice',
    overall_status: 'unavailable',
    overall_confidence: 0,
    review_required: false,
    issues: ['extraction_data_missing'],
    fields: [],
  },
})
check('12 no extraction data', missingData.includes('Field intelligence is unavailable because no invoice or purchase-order data has been extracted.') && missingData.includes('Approve'))

const clean = renderModal(review({ reason: 'low_extraction_confidence' }), {
  status: 'ready',
  error: '',
  report: {
    document_type: 'invoice',
    overall_status: 'valid',
    overall_confidence: 1,
    review_required: false,
    issues: [],
    fields: [
      { field_name: 'invoice_number', value: 'INV-1', status: 'valid', confidence: 1, issues: [] },
    ],
  },
})
check('5b no issues copy', clean.includes('No field-level issues detected.'))
check('8b low extraction explanation', clean.includes(REASON_EXPLANATIONS.low_extraction_confidence))

if (failures.length) {
  console.error(failures.join('\n'))
  process.exit(1)
}

console.log('review intelligence checks passed')
