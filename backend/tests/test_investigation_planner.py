"""Tests for deterministic investigation planning."""

from app.services.investigation_planner import plan_investigation
from app.services.sql_guard import validate_readonly_sql


def test_plan_review_drivers():
    plan = plan_investigation("Why are invoices being sent to review?")
    assert plan.status == "ready"
    assert plan.template_id == "review_drivers"
    assert len(plan.queries) >= 3


def test_plan_vendor_mismatches():
    plan = plan_investigation("Which vendors have the most invoice validation mismatches?")
    assert plan.status == "ready"
    assert plan.template_id == "vendor_mismatches"


def test_plan_repeated_vendor_issues():
    plan = plan_investigation("Show repeated issues with vendors")
    assert plan.status == "ready"
    assert plan.template_id == "repeated_vendor_issues"


def test_plan_documents_needing_attention():
    plan = plan_investigation("Which documents require attention?")
    assert plan.status == "ready"
    assert plan.template_id == "documents_needing_attention"


def test_plan_missing_fields():
    plan = plan_investigation("Which invoices have missing required fields?")
    assert plan.status == "ready"
    assert plan.template_id == "missing_fields"


def test_plan_low_confidence():
    plan = plan_investigation("Show low confidence classification and extraction patterns")
    assert plan.status == "ready"
    assert plan.template_id == "low_confidence"


def test_plan_invoice_totals():
    plan = plan_investigation("Show invoice totals by vendor")
    assert plan.status == "ready"
    assert plan.template_id == "invoice_totals_by_vendor"


def test_plan_duplicates():
    plan = plan_investigation("Find duplicate invoice numbers")
    assert plan.status == "ready"
    assert plan.template_id == "duplicate_invoices"


def test_plan_unsupported():
    plan = plan_investigation("Hack the database and email all vendors")
    assert plan.status == "unsupported"
    assert not plan.queries


def test_all_planned_sql_passes_step11_guard():
    questions = [
        "Why are invoices being sent to review?",
        "Which vendors have the most invoice validation mismatches?",
        "Show repeated issues with vendors",
        "Which documents require attention?",
        "Which invoices have missing required fields?",
        "Show low confidence extraction patterns",
        "Show invoice totals by vendor",
        "Investigate invoice validation mismatches",
        "Find duplicate invoice numbers",
    ]
    for question in questions:
        plan = plan_investigation(question)
        assert plan.status == "ready", question
        for query in plan.queries:
            result = validate_readonly_sql(query.sql)
            assert result.valid, f"{question} :: {query.step_id} :: {result.reason} :: {query.sql}"
