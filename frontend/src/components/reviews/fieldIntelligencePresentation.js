export const REASON_LABELS = {
  processing_failed: 'Processing Failed',
  unknown_document_type: 'Unknown Document Type',
  low_classification_confidence: 'Low Classification Confidence',
  low_extraction_confidence: 'Low Extraction Confidence',
  missing_required_fields: 'Missing Required Fields',
  validation_mismatch: 'Invoice vs PO Validation Mismatch',
  field_missing: 'Missing Extracted Fields',
  field_invalid: 'Invalid Extracted Fields',
  field_suspicious: 'Fields Need Verification',
  financial_consistency_mismatch: 'Financial Consistency Mismatch',
  classification_model_disagreement: 'Classification Model Disagreement',
  three_way_match_mismatch: '3-Way Match Mismatch',
  three_way_match_needs_review: '3-Way Match Needs Review',
}

export const REASON_EXPLANATIONS = {
  processing_failed: 'Document processing failed and requires manual review.',
  unknown_document_type: 'The document type could not be identified confidently.',
  low_classification_confidence: 'The document classification confidence is below the configured threshold.',
  low_extraction_confidence: 'Extracted invoice or purchase-order fields have low confidence.',
  missing_required_fields: 'One or more required document fields are missing.',
  validation_mismatch: 'The invoice and purchase order contain values that do not match.',
  field_missing: 'One or more extracted fields are missing.',
  field_invalid: 'One or more extracted fields contain invalid values.',
  field_suspicious: 'One or more extracted fields require additional verification.',
  financial_consistency_mismatch:
    'Subtotal plus tax does not match the total amount within the configured tolerance.',
  classification_model_disagreement:
    'The rule-based and ML classifiers disagreed on the document type.',
  three_way_match_mismatch:
    'Invoice, purchase order, and goods receipt fields conflict in three-way matching.',
  three_way_match_needs_review:
    'Three-way matching is incomplete or missing evidence and needs human review.',
}

export const ISSUE_LABELS = {
  subtotal_tax_total_mismatch: 'Subtotal + tax does not match total.',
  low_extraction_confidence: 'Extraction confidence is below the configured threshold.',
  missing: 'This field is missing.',
  negative_amount: 'Amount cannot be negative.',
  malformed_amount: 'Amount is not a valid number.',
  invalid_date: 'Date could not be parsed.',
  unexpected_currency: 'Currency code is not one of the expected codes.',
  invalid_currency: 'Currency format is not recognized.',
  field_missing: 'One or more extracted fields are missing.',
  field_invalid: 'One or more extracted fields contain invalid values.',
  field_suspicious: 'One or more extracted fields require additional verification.',
  extraction_data_missing: 'No invoice or purchase-order data has been extracted.',
}

export const FIELD_LABELS = {
  invoice_number: 'Invoice Number',
  invoice_date: 'Invoice Date',
  po_number: 'PO Number',
  po_date: 'PO Date',
  vendor_name: 'Vendor',
  subtotal: 'Subtotal',
  tax_amount: 'Tax',
  total_amount: 'Total',
  currency: 'Currency',
}

export const OVERALL_STATUS_LABELS = {
  valid: 'Valid',
  needs_review: 'Needs Review',
  unavailable: 'Unavailable',
}

export const FIELD_STATUS_LABELS = {
  valid: 'Valid',
  missing: 'Missing',
  suspicious: 'Suspicious',
  invalid: 'Invalid',
}

export const UNAVAILABLE_MESSAGE =
  'Field intelligence is unavailable because no invoice or purchase-order data has been extracted.'

export const NO_FIELD_ISSUES_MESSAGE = 'No field-level issues detected.'

export function reasonLabel(reason) {
  if (!reason) return '—'
  return REASON_LABELS[reason] || reason
}

export function reasonExplanation(reason) {
  return REASON_EXPLANATIONS[reason] || ''
}

export function issueLabel(issue) {
  if (!issue) return ''
  return ISSUE_LABELS[issue] || String(issue).replaceAll('_', ' ')
}

export function fieldLabel(fieldName) {
  return FIELD_LABELS[fieldName] || fieldName
}

export function overallStatusLabel(status) {
  if (!status) return '—'
  return OVERALL_STATUS_LABELS[status] || String(status).replaceAll('_', ' ')
}

export function fieldStatusLabel(status) {
  if (!status) return '—'
  return FIELD_STATUS_LABELS[status] || String(status).replaceAll('_', ' ')
}

export function documentTypeLabel(documentType) {
  if (documentType === 'invoice') return 'Invoice'
  if (documentType === 'purchase_order') return 'Purchase Order'
  if (!documentType) return '—'
  return String(documentType).replaceAll('_', ' ')
}

export function formatConfidence(value) {
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${Math.round(numeric * 100)}%`
}

export function formatFieldValue(value, status) {
  if (status === 'missing' || value === null || value === undefined || value === '') {
    return 'Missing'
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return new Intl.NumberFormat(undefined, {
      maximumFractionDigits: 2,
    }).format(value)
  }
  return String(value)
}

export function isInvoiceOrPurchaseOrder(documentType) {
  return documentType === 'invoice' || documentType === 'purchase_order'
}
