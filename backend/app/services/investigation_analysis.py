"""Deterministic analysis of investigation SQL results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AnalysisFinding:
    title: str
    description: str
    type: str  # fact | observation | inference


@dataclass
class AnalysisEvidence:
    description: str
    data: list[dict[str, Any]]
    step_id: str | None = None


@dataclass
class AnalysisResult:
    findings: list[AnalysisFinding]
    evidence: list[AnalysisEvidence]


def _scalar(rows: list[dict[str, Any]], key: str) -> Any | None:
    if not rows:
        return None
    if key in rows[0]:
        return rows[0].get(key)
    if len(rows[0]) == 1:
        return next(iter(rows[0].values()))
    return None


def analyze_investigation_results(
    template_id: str,
    step_results: list[dict[str, Any]],
) -> AnalysisResult:
    """
    Build findings and evidence strictly from returned SQL rows.

    step_results items:
      {
        "step_id", "question", "sql", "analysis_key",
        "columns", "rows", "row_count", "error"
      }
    """
    findings: list[AnalysisFinding] = []
    evidence: list[AnalysisEvidence] = []
    by_key = {item["analysis_key"]: item for item in step_results if item.get("analysis_key")}

    for item in step_results:
        if item.get("error"):
            findings.append(
                AnalysisFinding(
                    title=f"Query issue: {item.get('step_id', 'step')}",
                    description=(
                        f"The investigation step '{item.get('question')}' could not be completed. "
                        "No data from this step is included as evidence."
                    ),
                    type="observation",
                )
            )
            continue

        rows = item.get("rows") or []
        evidence.append(
            AnalysisEvidence(
                description=item.get("question") or item.get("step_id") or "Query result",
                data=rows,
                step_id=item.get("step_id"),
            )
        )

    if template_id == "review_drivers":
        findings.extend(_analyze_review_drivers(by_key))
    elif template_id == "vendor_mismatches":
        findings.extend(_analyze_vendor_mismatches(by_key))
    elif template_id == "repeated_vendor_issues":
        findings.extend(_analyze_repeated_vendor_issues(by_key))
    elif template_id == "documents_needing_attention":
        findings.extend(_analyze_documents_needing_attention(by_key))
    elif template_id == "missing_fields":
        findings.extend(_analyze_missing_fields(by_key))
    elif template_id == "low_confidence":
        findings.extend(_analyze_low_confidence(by_key))
    elif template_id == "invoice_totals_by_vendor":
        findings.extend(_analyze_invoice_totals(by_key))
    elif template_id == "validation_mismatches":
        findings.extend(_analyze_validation_mismatches(by_key))
    elif template_id == "duplicate_invoices":
        findings.extend(_analyze_duplicates(by_key))
    else:
        findings.append(
            AnalysisFinding(
                title="Investigation completed",
                description="Structured query results are available in the evidence section.",
                type="observation",
            )
        )

    if not findings:
        findings.append(
            AnalysisFinding(
                title="No findings derived",
                description=(
                    "Queries completed, but the returned data did not contain enough "
                    "information to state additional findings."
                ),
                type="observation",
            )
        )

    return AnalysisResult(findings=findings, evidence=evidence)


def _analyze_review_drivers(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    findings: list[AnalysisFinding] = []
    active = _scalar((by_key.get("active_review_count") or {}).get("rows") or [], "active_review_count")
    if active is not None:
        findings.append(
            AnalysisFinding(
                title="Active review items",
                description=f"There are currently {active} active review items (pending or in review).",
                type="fact",
            )
        )

    reason_rows = (by_key.get("reviews_by_reason") or {}).get("rows") or []
    if reason_rows:
        top = reason_rows[0]
        findings.append(
            AnalysisFinding(
                title="Most common review reason",
                description=(
                    f"The most frequent active review reason is '{top.get('reason')}' "
                    f"with {top.get('review_count')} item(s)."
                ),
                type="fact",
            )
        )
        if len(reason_rows) > 1:
            findings.append(
                AnalysisFinding(
                    title="Multiple review drivers",
                    description=(
                        f"Active reviews span {len(reason_rows)} distinct reason codes, "
                        "indicating more than one driver may be sending items to review."
                    ),
                    type="observation",
                )
            )
    elif active == 0:
        findings.append(
            AnalysisFinding(
                title="No active reviews",
                description="No pending or in-review items were found in the review queue.",
                type="fact",
            )
        )

    mismatch = _scalar((by_key.get("mismatch_count") or {}).get("rows") or [], "mismatch_count")
    if mismatch is not None:
        findings.append(
            AnalysisFinding(
                title="Validation mismatches",
                description=f"There are {mismatch} invoice/PO validation mismatch record(s).",
                type="fact",
            )
        )
        if isinstance(mismatch, (int, float)) and mismatch > 0 and isinstance(active, (int, float)) and active > 0:
            findings.append(
                AnalysisFinding(
                    title="Possible relationship to review volume",
                    description=(
                        "Validation mismatches exist alongside active reviews. "
                        "This may contribute to review volume, but causality is not proven by these counts alone."
                    ),
                    type="inference",
                )
            )

    low_ext = _scalar(
        (by_key.get("low_extraction_count") or {}).get("rows") or [],
        "low_extraction_count",
    )
    if low_ext is not None:
        findings.append(
            AnalysisFinding(
                title="Low extraction confidence invoices",
                description=(
                    f"{low_ext} invoice(s) have extraction_confidence below 0.7 "
                    "(where confidence is present)."
                ),
                type="fact",
            )
        )

    missing = _scalar(
        (by_key.get("missing_invoice_fields") or {}).get("rows") or [],
        "missing_field_invoice_count",
    )
    if missing is not None:
        findings.append(
            AnalysisFinding(
                title="Invoices with missing key fields",
                description=(
                    f"{missing} invoice(s) are missing one or more of: "
                    "invoice_number, total_amount, vendor_name, currency."
                ),
                type="fact",
            )
        )

    return findings


def _analyze_vendor_mismatches(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    findings: list[AnalysisFinding] = []
    total = _scalar((by_key.get("mismatch_count") or {}).get("rows") or [], "mismatch_count")
    if total is not None:
        findings.append(
            AnalysisFinding(
                title="Total mismatches",
                description=f"Observed validation mismatch count is {total}.",
                type="fact",
            )
        )

    rows = (by_key.get("mismatches_by_vendor") or {}).get("rows") or []
    if not rows:
        findings.append(
            AnalysisFinding(
                title="No vendor-level mismatch rows",
                description="No vendor-grouped mismatch rows were returned.",
                type="fact",
            )
        )
    else:
        top = rows[0]
        findings.append(
            AnalysisFinding(
                title="Highest observed mismatch volume by vendor",
                description=(
                    f"Vendor '{top.get('vendor_name')}' appears in "
                    f"{top.get('mismatch_count')} mismatch record(s). "
                    "This is an observed count, not a quality score."
                ),
                type="fact",
            )
        )
        repeated = [row for row in rows if (row.get("mismatch_count") or 0) > 1]
        if repeated:
            findings.append(
                AnalysisFinding(
                    title="Vendors with repeated mismatches",
                    description=(
                        f"{len(repeated)} vendor name(s) appear in more than one mismatch record."
                    ),
                    type="observation",
                )
            )

    vendor_flags = _scalar(
        (by_key.get("vendor_flag_mismatch_count") or {}).get("rows") or [],
        "vendor_flag_mismatch_count",
    )
    if vendor_flags is not None:
        findings.append(
            AnalysisFinding(
                title="Explicit vendor_match failures",
                description=f"{vendor_flags} validation(s) have vendor_match = false.",
                type="fact",
            )
        )
    return findings


def _analyze_repeated_vendor_issues(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    findings = _analyze_vendor_mismatches(
        {
            "mismatch_count": {
                "rows": [
                    {
                        "mismatch_count": sum(
                            int(row.get("mismatch_count") or 0)
                            for row in ((by_key.get("mismatches_by_vendor") or {}).get("rows") or [])
                        )
                    }
                ]
            },
            "mismatches_by_vendor": by_key.get("mismatches_by_vendor") or {"rows": []},
            "vendor_flag_mismatch_count": {"rows": []},
        }
    )
    review_rows = (by_key.get("reviews_by_vendor_reason") or {}).get("rows") or []
    if review_rows:
        findings.append(
            AnalysisFinding(
                title="Review activity linked to vendors",
                description=(
                    f"Found {len(review_rows)} vendor/reason aggregate row(s) among active reviews."
                ),
                type="fact",
            )
        )
        multi = [row for row in review_rows if (row.get("review_count") or 0) > 1]
        if multi:
            findings.append(
                AnalysisFinding(
                    title="Repeated review pattern",
                    description=(
                        f"{len(multi)} vendor/reason combination(s) appear more than once "
                        "in active reviews."
                    ),
                    type="observation",
                )
            )
    return findings


def _analyze_documents_needing_attention(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    findings: list[AnalysisFinding] = []
    attention = (by_key.get("attention_documents") or {}).get("rows") or []
    failed = (by_key.get("failed_documents") or {}).get("rows") or []
    mismatches = (by_key.get("mismatch_rows") or {}).get("rows") or []

    findings.append(
        AnalysisFinding(
            title="Review queue documents",
            description=f"{len(attention)} document(s) currently require review attention.",
            type="fact",
        )
    )
    findings.append(
        AnalysisFinding(
            title="Failed documents",
            description=f"{len(failed)} document(s) have status 'failed'.",
            type="fact",
        )
    )
    findings.append(
        AnalysisFinding(
            title="Validation mismatches",
            description=f"{len(mismatches)} validation mismatch record(s) were returned.",
            type="fact",
        )
    )
    if attention or failed or mismatches:
        findings.append(
            AnalysisFinding(
                title="Attention summary",
                description=(
                    "Documents needing attention were identified from review queue, "
                    "failed processing status, and validation mismatches."
                ),
                type="observation",
            )
        )
    return findings


def _analyze_missing_fields(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    inv = (by_key.get("missing_invoice_rows") or {}).get("rows") or []
    pos = (by_key.get("missing_po_rows") or {}).get("rows") or []
    review_count = _scalar(
        (by_key.get("missing_field_review_count") or {}).get("rows") or [],
        "missing_field_review_count",
    )
    findings = [
        AnalysisFinding(
            title="Invoices with missing fields",
            description=f"{len(inv)} invoice row(s) are missing one or more key fields.",
            type="fact",
        ),
        AnalysisFinding(
            title="Purchase orders with missing fields",
            description=f"{len(pos)} purchase-order row(s) are missing one or more key fields.",
            type="fact",
        ),
    ]
    if review_count is not None:
        findings.append(
            AnalysisFinding(
                title="Missing-field reviews",
                description=(
                    f"{review_count} active review item(s) have reason "
                    "'missing_required_fields'."
                ),
                type="fact",
            )
        )
    return findings


def _analyze_low_confidence(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    cls_rows = (by_key.get("low_classification_rows") or {}).get("rows") or []
    ext_rows = (by_key.get("low_extraction_invoice_rows") or {}).get("rows") or []
    findings = [
        AnalysisFinding(
            title="Low classification confidence documents",
            description=(
                f"{len(cls_rows)} document(s) have classification_confidence below 0.7."
            ),
            type="fact",
        ),
        AnalysisFinding(
            title="Low extraction confidence invoices",
            description=f"{len(ext_rows)} invoice(s) have extraction_confidence below 0.7.",
            type="fact",
        ),
    ]
    review_rows = (by_key.get("low_confidence_reviews") or {}).get("rows") or []
    if review_rows:
        parts = [
            f"{row.get('reason')}: {row.get('review_count')}" for row in review_rows
        ]
        findings.append(
            AnalysisFinding(
                title="Low-confidence review reasons",
                description="Active low-confidence reviews — " + "; ".join(parts) + ".",
                type="fact",
            )
        )
    return findings


def _analyze_invoice_totals(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    rows = (by_key.get("invoice_totals_by_vendor") or {}).get("rows") or []
    if not rows:
        return [
            AnalysisFinding(
                title="No invoice totals",
                description="No invoice total rows were returned.",
                type="fact",
            )
        ]
    top = rows[0]
    return [
        AnalysisFinding(
            title="Vendor with highest observed invoice total",
            description=(
                f"Vendor '{top.get('vendor_name')}' has observed invoice_total "
                f"{top.get('invoice_total')} across {top.get('invoice_count')} invoice(s)."
            ),
            type="fact",
        ),
        AnalysisFinding(
            title="Vendors included",
            description=f"Invoice totals were aggregated for {len(rows)} vendor group(s).",
            type="fact",
        ),
    ]


def _analyze_validation_mismatches(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    findings: list[AnalysisFinding] = []
    total = _scalar((by_key.get("mismatch_count") or {}).get("rows") or [], "mismatch_count")
    if total is not None:
        findings.append(
            AnalysisFinding(
                title="Mismatch count",
                description=f"There are {total} validation mismatch record(s).",
                type="fact",
            )
        )
    breakdown = (by_key.get("mismatch_flag_breakdown") or {}).get("rows") or []
    if breakdown:
        row = breakdown[0]
        parts = []
        for key in (
            "vendor_mismatches",
            "currency_mismatches",
            "subtotal_mismatches",
            "tax_mismatches",
            "total_mismatches",
        ):
            if key in row and row[key] is not None:
                parts.append(f"{key.replace('_', ' ')}={row[key]}")
        if parts:
            findings.append(
                AnalysisFinding(
                    title="Mismatch flag breakdown",
                    description="Among mismatch records: " + "; ".join(parts) + ".",
                    type="fact",
                )
            )
    detail_rows = (by_key.get("mismatch_rows") or {}).get("rows") or []
    findings.append(
        AnalysisFinding(
            title="Mismatch detail rows",
            description=f"{len(detail_rows)} mismatch detail row(s) were returned as evidence.",
            type="fact",
        )
    )
    return findings


def _analyze_duplicates(by_key: dict[str, dict[str, Any]]) -> list[AnalysisFinding]:
    dup_numbers = (by_key.get("duplicate_invoice_numbers") or {}).get("rows") or []
    dup_rows = (by_key.get("duplicate_invoice_rows") or {}).get("rows") or []
    findings = [
        AnalysisFinding(
            title="Duplicated invoice numbers",
            description=(
                f"{len(dup_numbers)} invoice_number value(s) appear more than once."
            ),
            type="fact",
        ),
        AnalysisFinding(
            title="Rows sharing duplicated numbers",
            description=f"{len(dup_rows)} invoice row(s) are associated with duplicated numbers.",
            type="fact",
        ),
    ]
    if dup_numbers:
        findings.append(
            AnalysisFinding(
                title="Possible duplicates",
                description=(
                    "Repeated invoice numbers may indicate re-uploads or true duplicates; "
                    "manual document comparison is required to confirm."
                ),
                type="inference",
            )
        )
    else:
        findings.append(
            AnalysisFinding(
                title="No duplicate numbers found",
                description="No invoice_number values with occurrence_count > 1 were returned.",
                type="fact",
            )
        )
    return findings
