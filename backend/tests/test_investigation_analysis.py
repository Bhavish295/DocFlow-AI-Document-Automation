"""Tests for deterministic investigation analysis."""

from app.services.investigation_analysis import analyze_investigation_results


def test_analysis_uses_only_returned_data():
    step_results = [
        {
            "step_id": "active_review_count",
            "question": "active reviews",
            "sql": "SELECT 1",
            "analysis_key": "active_review_count",
            "columns": ["active_review_count"],
            "rows": [{"active_review_count": 3}],
            "row_count": 1,
            "error": None,
        },
        {
            "step_id": "reviews_by_reason",
            "question": "by reason",
            "sql": "SELECT 1",
            "analysis_key": "reviews_by_reason",
            "columns": ["reason", "review_count"],
            "rows": [{"reason": "validation_mismatch", "review_count": 2}],
            "row_count": 1,
            "error": None,
        },
        {
            "step_id": "validation_mismatch_count",
            "question": "mismatches",
            "sql": "SELECT 1",
            "analysis_key": "mismatch_count",
            "columns": ["mismatch_count"],
            "rows": [{"mismatch_count": 2}],
            "row_count": 1,
            "error": None,
        },
        {
            "step_id": "low_extraction_invoices",
            "question": "low extraction",
            "sql": "SELECT 1",
            "analysis_key": "low_extraction_count",
            "columns": ["low_extraction_count"],
            "rows": [{"low_extraction_count": 0}],
            "row_count": 1,
            "error": None,
        },
        {
            "step_id": "missing_invoice_fields",
            "question": "missing",
            "sql": "SELECT 1",
            "analysis_key": "missing_invoice_fields",
            "columns": ["missing_field_invoice_count"],
            "rows": [{"missing_field_invoice_count": 1}],
            "row_count": 1,
            "error": None,
        },
    ]
    result = analyze_investigation_results("review_drivers", step_results)
    assert result.findings
    assert any(finding.type == "fact" for finding in result.findings)
    joined = " ".join(finding.description for finding in result.findings)
    assert "3" in joined
    assert "validation_mismatch" in joined
    assert "999" not in joined  # no fabricated values


def test_analysis_empty_results():
    result = analyze_investigation_results(
        "documents_needing_attention",
        [
            {
                "step_id": "active_reviews",
                "question": "reviews",
                "sql": "SELECT 1",
                "analysis_key": "attention_documents",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": None,
            },
            {
                "step_id": "failed_documents",
                "question": "failed",
                "sql": "SELECT 1",
                "analysis_key": "failed_documents",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": None,
            },
            {
                "step_id": "mismatch_validations",
                "question": "mismatches",
                "sql": "SELECT 1",
                "analysis_key": "mismatch_rows",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": None,
            },
        ],
    )
    assert any("0 document(s) currently require review" in f.description for f in result.findings)


def test_analysis_marks_query_errors():
    result = analyze_investigation_results(
        "review_drivers",
        [
            {
                "step_id": "broken",
                "question": "broken step",
                "sql": "SELECT 1",
                "analysis_key": "active_review_count",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": "boom",
            }
        ],
    )
    assert any(f.type == "observation" and "could not be completed" in f.description for f in result.findings)
