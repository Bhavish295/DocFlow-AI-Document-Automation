"""Deterministic investigation planning for common business questions."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PlannedQuery:
    """One read-only investigation step with pre-approved SELECT SQL."""

    step_id: str
    question: str
    sql: str
    analysis_key: str


@dataclass(frozen=True)
class InvestigationPlan:
    template_id: str
    title: str
    status: str  # ready | unsupported
    queries: tuple[PlannedQuery, ...] = ()
    unsupported_message: str | None = None
    suggested_next_steps: tuple[str, ...] = ()


SUPPORTED_INVESTIGATION_TYPES = (
    "invoice review reasons and review-queue drivers",
    "validation mismatch patterns",
    "vendor mismatch / repeated vendor issues",
    "documents requiring attention",
    "missing invoice or purchase-order fields",
    "low classification or extraction confidence",
    "invoice totals by vendor",
    "possible duplicate invoice numbers",
)


def _normalize(question: str) -> str:
    cleaned = (question or "").strip().lower()
    cleaned = cleaned.replace("?", " ")
    cleaned = re.sub(r"[^\w\s./-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def plan_investigation(question: str) -> InvestigationPlan:
    """Map a natural-language investigation question to a deterministic plan."""
    q = _normalize(question)
    if not q:
        return InvestigationPlan(
            template_id="empty",
            title="Empty question",
            status="unsupported",
            unsupported_message="Please enter an investigation question.",
        )

    # Why invoices / documents go to review
    if (
        re.search(r"\bwhy\b.*\b(invoices?|documents?)\b.*\breview\b", q)
        or re.search(r"\b(invoices?|documents?)\b.*\b(sent|going|requir)\w*\b.*\breview\b", q)
        or "review required" in q
        or "why are invoices being sent to review" in q
    ):
        return _plan_review_drivers()

    # Vendor mismatch ranking / which vendors have mismatches
    if (
        re.search(r"\bvendors?\b.*\b(mismatch|mismatches|validation)\b", q)
        or re.search(r"\b(mismatch|mismatches)\b.*\bvendors?\b", q)
        or "validation mismatches" in q and "vendor" in q
    ):
        return _plan_vendor_mismatches()

    # Repeated vendor issues
    if (
        re.search(r"\brepeated\b.*\b(issues?|problems?|mismatches?)\b.*\bvendors?\b", q)
        or re.search(r"\brepeated\b.*\bvendors?\b", q)
        or "repeated issues with vendors" in q
    ):
        return _plan_repeated_vendor_issues()

    # Documents requiring attention
    if (
        re.search(r"\b(documents?|items?)\b.*\b(require|need|needing)\b.*\b(attention|review)\b", q)
        or "which documents require attention" in q
        or "documents needing review" in q
    ):
        return _plan_documents_needing_attention()

    # Missing fields
    if (
        re.search(r"\bmissing\b.*\b(fields?|invoice|purchase order|po)\b", q)
        or "incomplete invoice" in q
        or "missing required fields" in q
    ):
        return _plan_missing_fields()

    # Low confidence
    if (
        re.search(r"\blow[ -]?confidence\b", q)
        or re.search(r"\b(classification|extraction)\b.*\bconfidence\b", q)
        or "uncertain classification" in q
    ):
        return _plan_low_confidence()

    # Invoice totals by vendor
    if (
        re.search(r"\binvoice totals?\b.*\bby vendor\b", q)
        or re.search(r"\btotals?\b.*\binvoices?\b.*\bvendors?\b", q)
        or "invoice totals by vendor" in q
    ):
        return _plan_invoice_totals_by_vendor()

    # Validation mismatches general
    if (
        re.search(r"\bvalidation mismatches?\b", q)
        or re.search(r"\binvoice\b.*\bpurchase order\b.*\bmismatch", q)
        or "invoice validation" in q
    ):
        return _plan_validation_mismatches()

    # Duplicate invoices
    if (
        re.search(r"\bduplicate\b.*\binvoices?\b", q)
        or re.search(r"\bsimilar\b.*\binvoices?\b", q)
        or "duplicate invoice numbers" in q
    ):
        return _plan_duplicate_invoices()

    # Generic review queue investigation
    if re.search(r"\breview queue\b", q) or re.search(r"\bpending reviews?\b", q):
        return _plan_review_drivers()

    return InvestigationPlan(
        template_id="unsupported",
        title="Unsupported investigation",
        status="unsupported",
        unsupported_message=(
            "I cannot safely investigate that question with the current controlled planner. "
            "Supported investigation types include: "
            + "; ".join(SUPPORTED_INVESTIGATION_TYPES)
            + "."
        ),
    )


def _plan_review_drivers() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="review_drivers",
        title="Review queue drivers",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="active_review_count",
                question="How many review items are currently active?",
                sql=(
                    "SELECT COUNT(*) AS active_review_count FROM document_reviews "
                    "WHERE status IN ('pending', 'in_review')"
                ),
                analysis_key="active_review_count",
            ),
            PlannedQuery(
                step_id="reviews_by_reason",
                question="How are active reviews grouped by reason?",
                sql=(
                    "SELECT reason, COUNT(*) AS review_count FROM document_reviews "
                    "WHERE status IN ('pending', 'in_review') "
                    "GROUP BY reason ORDER BY review_count DESC"
                ),
                analysis_key="reviews_by_reason",
            ),
            PlannedQuery(
                step_id="validation_mismatch_count",
                question="How many invoice/PO validation mismatches exist?",
                sql=(
                    "SELECT COUNT(*) AS mismatch_count FROM document_validations "
                    "WHERE status = 'mismatch'"
                ),
                analysis_key="mismatch_count",
            ),
            PlannedQuery(
                step_id="low_extraction_invoices",
                question="How many invoices have low extraction confidence?",
                sql=(
                    "SELECT COUNT(*) AS low_extraction_count FROM invoices "
                    "WHERE extraction_confidence IS NOT NULL AND extraction_confidence < 0.7"
                ),
                analysis_key="low_extraction_count",
            ),
            PlannedQuery(
                step_id="missing_invoice_fields",
                question="How many invoices are missing key fields?",
                sql=(
                    "SELECT COUNT(*) AS missing_field_invoice_count FROM invoices "
                    "WHERE invoice_number IS NULL OR total_amount IS NULL "
                    "OR vendor_name IS NULL OR currency IS NULL"
                ),
                analysis_key="missing_invoice_fields",
            ),
            PlannedQuery(
                step_id="review_documents",
                question="Which documents are currently in the review queue?",
                sql=(
                    "SELECT d.original_filename AS filename, d.document_type, "
                    "r.reason, r.priority, r.status "
                    "FROM document_reviews r "
                    "JOIN documents d ON d.id = r.document_id "
                    "WHERE r.status IN ('pending', 'in_review') "
                    "ORDER BY r.created_at DESC"
                ),
                analysis_key="review_documents",
            ),
        ),
        suggested_next_steps=(
            "Open the Review Queue and prioritize high-priority pending items.",
            "Inspect validation mismatches for invoices linked to review items.",
            "Re-check documents with missing invoice fields or low extraction confidence.",
        ),
    )


def _plan_vendor_mismatches() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="vendor_mismatches",
        title="Vendor validation mismatch counts",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="mismatch_total",
                question="How many validation mismatches exist overall?",
                sql=(
                    "SELECT COUNT(*) AS mismatch_count FROM document_validations "
                    "WHERE status = 'mismatch'"
                ),
                analysis_key="mismatch_count",
            ),
            PlannedQuery(
                step_id="mismatches_by_vendor",
                question="How many validation mismatches are observed per vendor?",
                sql=(
                    "SELECT COALESCE(v.name, i.vendor_name, 'Unknown') AS vendor_name, "
                    "COUNT(*) AS mismatch_count "
                    "FROM document_validations dv "
                    "JOIN invoices i ON i.id = dv.invoice_id "
                    "LEFT JOIN vendors v ON v.id = i.vendor_id "
                    "WHERE dv.status = 'mismatch' "
                    "GROUP BY COALESCE(v.name, i.vendor_name, 'Unknown') "
                    "ORDER BY mismatch_count DESC"
                ),
                analysis_key="mismatches_by_vendor",
            ),
            PlannedQuery(
                step_id="vendor_match_false",
                question="How many validations recorded an explicit vendor mismatch flag?",
                sql=(
                    "SELECT COUNT(*) AS vendor_flag_mismatch_count FROM document_validations "
                    "WHERE vendor_match IS NOT NULL AND NOT vendor_match"
                ),
                analysis_key="vendor_flag_mismatch_count",
            ),
        ),
        suggested_next_steps=(
            "Review vendors with the highest observed mismatch counts in the Validation page.",
            "Compare invoice and purchase-order vendor names for those vendors.",
            "Do not treat counts as a vendor quality score — they are observed mismatch volumes only.",
        ),
    )


def _plan_repeated_vendor_issues() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="repeated_vendor_issues",
        title="Repeated vendor issue patterns",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="mismatches_by_vendor",
                question="Observed validation mismatch counts by vendor",
                sql=(
                    "SELECT COALESCE(v.name, i.vendor_name, 'Unknown') AS vendor_name, "
                    "COUNT(*) AS mismatch_count "
                    "FROM document_validations dv "
                    "JOIN invoices i ON i.id = dv.invoice_id "
                    "LEFT JOIN vendors v ON v.id = i.vendor_id "
                    "WHERE dv.status = 'mismatch' "
                    "GROUP BY COALESCE(v.name, i.vendor_name, 'Unknown') "
                    "ORDER BY mismatch_count DESC"
                ),
                analysis_key="mismatches_by_vendor",
            ),
            PlannedQuery(
                step_id="reviews_by_vendor_docs",
                question="Review reasons for documents linked to invoices with vendors",
                sql=(
                    "SELECT COALESCE(v.name, i.vendor_name, 'Unknown') AS vendor_name, "
                    "r.reason, COUNT(*) AS review_count "
                    "FROM document_reviews r "
                    "JOIN documents d ON d.id = r.document_id "
                    "LEFT JOIN invoices i ON i.document_id = d.id "
                    "LEFT JOIN vendors v ON v.id = i.vendor_id "
                    "WHERE r.status IN ('pending', 'in_review') "
                    "GROUP BY COALESCE(v.name, i.vendor_name, 'Unknown'), r.reason "
                    "ORDER BY review_count DESC"
                ),
                analysis_key="reviews_by_vendor_reason",
            ),
        ),
        suggested_next_steps=(
            "Focus manual review on vendors that appear more than once in mismatch or review aggregates.",
            "Verify vendor master records and invoice/PO naming consistency.",
        ),
    )


def _plan_documents_needing_attention() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="documents_needing_attention",
        title="Documents requiring attention",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="active_reviews",
                question="Documents currently in the review queue",
                sql=(
                    "SELECT d.id AS document_id, d.original_filename AS filename, "
                    "d.document_type, d.status AS document_status, "
                    "r.reason, r.priority, r.status AS review_status "
                    "FROM document_reviews r "
                    "JOIN documents d ON d.id = r.document_id "
                    "WHERE r.status IN ('pending', 'in_review') "
                    "ORDER BY r.created_at DESC"
                ),
                analysis_key="attention_documents",
            ),
            PlannedQuery(
                step_id="failed_documents",
                question="Documents with failed processing status",
                sql=(
                    "SELECT id AS document_id, original_filename AS filename, "
                    "document_type, status "
                    "FROM documents WHERE status = 'failed' "
                    "ORDER BY uploaded_at DESC"
                ),
                analysis_key="failed_documents",
            ),
            PlannedQuery(
                step_id="mismatch_validations",
                question="Validation mismatches that may need attention",
                sql=(
                    "SELECT dv.id AS validation_id, dv.status, dv.invoice_number, "
                    "dv.po_number, i.vendor_name "
                    "FROM document_validations dv "
                    "JOIN invoices i ON i.id = dv.invoice_id "
                    "WHERE dv.status = 'mismatch' "
                    "ORDER BY dv.created_at DESC"
                ),
                analysis_key="mismatch_rows",
            ),
        ),
        suggested_next_steps=(
            "Open the Review Queue for pending and in-review documents.",
            "Inspect failed documents and re-process if appropriate.",
            "Resolve validation mismatches on the Validation page.",
        ),
    )


def _plan_missing_fields() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="missing_fields",
        title="Missing invoice and purchase-order fields",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="missing_invoices",
                question="Invoices missing key extracted fields",
                sql=(
                    "SELECT i.invoice_number, i.vendor_name, i.total_amount, i.currency, "
                    "d.original_filename AS filename "
                    "FROM invoices i "
                    "JOIN documents d ON d.id = i.document_id "
                    "WHERE i.invoice_number IS NULL OR i.total_amount IS NULL "
                    "OR i.vendor_name IS NULL OR i.currency IS NULL "
                    "ORDER BY i.created_at DESC"
                ),
                analysis_key="missing_invoice_rows",
            ),
            PlannedQuery(
                step_id="missing_pos",
                question="Purchase orders missing key extracted fields",
                sql=(
                    "SELECT p.po_number, p.vendor_name, p.total_amount, p.currency, "
                    "d.original_filename AS filename "
                    "FROM purchase_orders p "
                    "JOIN documents d ON d.id = p.document_id "
                    "WHERE p.po_number IS NULL OR p.total_amount IS NULL "
                    "OR p.vendor_name IS NULL OR p.currency IS NULL "
                    "ORDER BY p.created_at DESC"
                ),
                analysis_key="missing_po_rows",
            ),
            PlannedQuery(
                step_id="missing_field_reviews",
                question="Reviews created for missing required fields",
                sql=(
                    "SELECT COUNT(*) AS missing_field_review_count FROM document_reviews "
                    "WHERE reason = 'missing_required_fields' "
                    "AND status IN ('pending', 'in_review')"
                ),
                analysis_key="missing_field_review_count",
            ),
        ),
        suggested_next_steps=(
            "Open affected documents and verify OCR/extraction quality.",
            "Manually complete missing fields during review when needed.",
        ),
    )


def _plan_low_confidence() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="low_confidence",
        title="Low classification and extraction confidence",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="low_classification_docs",
                question="Documents with low classification confidence",
                sql=(
                    "SELECT original_filename AS filename, document_type, "
                    "classification_confidence, status "
                    "FROM documents "
                    "WHERE classification_confidence IS NOT NULL "
                    "AND classification_confidence < 0.7 "
                    "ORDER BY classification_confidence ASC"
                ),
                analysis_key="low_classification_rows",
            ),
            PlannedQuery(
                step_id="low_extraction_invoices",
                question="Invoices with low extraction confidence",
                sql=(
                    "SELECT i.invoice_number, i.vendor_name, i.extraction_confidence, "
                    "d.original_filename AS filename "
                    "FROM invoices i "
                    "JOIN documents d ON d.id = i.document_id "
                    "WHERE i.extraction_confidence IS NOT NULL "
                    "AND i.extraction_confidence < 0.7 "
                    "ORDER BY i.extraction_confidence ASC"
                ),
                analysis_key="low_extraction_invoice_rows",
            ),
            PlannedQuery(
                step_id="low_confidence_reviews",
                question="Active reviews related to low confidence",
                sql=(
                    "SELECT reason, COUNT(*) AS review_count FROM document_reviews "
                    "WHERE status IN ('pending', 'in_review') "
                    "AND reason IN ('low_classification_confidence', 'low_extraction_confidence') "
                    "GROUP BY reason ORDER BY review_count DESC"
                ),
                analysis_key="low_confidence_reviews",
            ),
        ),
        suggested_next_steps=(
            "Review low-confidence documents in the Review Queue.",
            "Confirm document type and extracted fields before approving.",
        ),
    )


def _plan_invoice_totals_by_vendor() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="invoice_totals_by_vendor",
        title="Invoice totals by vendor",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="totals_by_vendor",
                question="Sum of invoice totals grouped by vendor",
                sql=(
                    "SELECT COALESCE(vendor_name, 'Unknown') AS vendor_name, "
                    "COUNT(*) AS invoice_count, "
                    "COALESCE(SUM(total_amount), 0) AS invoice_total "
                    "FROM invoices "
                    "GROUP BY vendor_name "
                    "ORDER BY invoice_total DESC"
                ),
                analysis_key="invoice_totals_by_vendor",
            ),
        ),
        suggested_next_steps=(
            "Use the Business Data assistant for follow-up totals filters if needed.",
            "Cross-check large vendor totals against purchase orders when investigating exceptions.",
        ),
    )


def _plan_validation_mismatches() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="validation_mismatches",
        title="Invoice validation mismatch investigation",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="mismatch_count",
                question="Total validation mismatches",
                sql=(
                    "SELECT COUNT(*) AS mismatch_count FROM document_validations "
                    "WHERE status = 'mismatch'"
                ),
                analysis_key="mismatch_count",
            ),
            PlannedQuery(
                step_id="mismatch_flag_breakdown",
                question="Which match flags failed most often?",
                sql=(
                    "SELECT "
                    "SUM(CASE WHEN vendor_match IS NOT NULL AND NOT vendor_match THEN 1 ELSE 0 END) AS vendor_mismatches, "
                    "SUM(CASE WHEN currency_match IS NOT NULL AND NOT currency_match THEN 1 ELSE 0 END) AS currency_mismatches, "
                    "SUM(CASE WHEN subtotal_match IS NOT NULL AND NOT subtotal_match THEN 1 ELSE 0 END) AS subtotal_mismatches, "
                    "SUM(CASE WHEN tax_match IS NOT NULL AND NOT tax_match THEN 1 ELSE 0 END) AS tax_mismatches, "
                    "SUM(CASE WHEN total_match IS NOT NULL AND NOT total_match THEN 1 ELSE 0 END) AS total_mismatches "
                    "FROM document_validations WHERE status = 'mismatch'"
                ),
                analysis_key="mismatch_flag_breakdown",
            ),
            PlannedQuery(
                step_id="mismatch_details",
                question="Recent mismatch records",
                sql=(
                    "SELECT dv.invoice_number, dv.po_number, i.vendor_name, "
                    "dv.vendor_match, dv.total_match, dv.currency_match "
                    "FROM document_validations dv "
                    "JOIN invoices i ON i.id = dv.invoice_id "
                    "WHERE dv.status = 'mismatch' "
                    "ORDER BY dv.created_at DESC"
                ),
                analysis_key="mismatch_rows",
            ),
        ),
        suggested_next_steps=(
            "Inspect the Validation page for mismatch details.",
            "Confirm whether amount, vendor, or currency differences are expected.",
        ),
    )


def _plan_duplicate_invoices() -> InvestigationPlan:
    return InvestigationPlan(
        template_id="duplicate_invoices",
        title="Possible duplicate invoice numbers",
        status="ready",
        queries=(
            PlannedQuery(
                step_id="duplicate_invoice_numbers",
                question="Invoice numbers that appear more than once",
                sql=(
                    "SELECT invoice_number, COUNT(*) AS occurrence_count "
                    "FROM invoices "
                    "WHERE invoice_number IS NOT NULL "
                    "GROUP BY invoice_number "
                    "HAVING COUNT(*) > 1 "
                    "ORDER BY occurrence_count DESC"
                ),
                analysis_key="duplicate_invoice_numbers",
            ),
            PlannedQuery(
                step_id="duplicate_invoice_rows",
                question="Invoice rows for duplicated invoice numbers",
                sql=(
                    "SELECT i.invoice_number, i.vendor_name, i.total_amount, "
                    "d.original_filename AS filename "
                    "FROM invoices i "
                    "JOIN documents d ON d.id = i.document_id "
                    "WHERE i.invoice_number IN ("
                    "SELECT invoice_number FROM invoices "
                    "WHERE invoice_number IS NOT NULL "
                    "GROUP BY invoice_number HAVING COUNT(*) > 1"
                    ") "
                    "ORDER BY i.invoice_number"
                ),
                analysis_key="duplicate_invoice_rows",
            ),
        ),
        suggested_next_steps=(
            "Manually compare documents that share an invoice number.",
            "Confirm whether duplicates are re-uploads or true business duplicates.",
        ),
    )
