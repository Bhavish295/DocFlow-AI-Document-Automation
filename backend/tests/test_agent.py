import io
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.permissions import Permission, role_has_permission
from app.core.security import create_access_token
from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.user import UserRole
from app.services.agent.agent_planner import DeterministicAgentPlanner
from app.services.agent.agent_registry import AgentToolDefinition, AgentToolRegistry
from app.services.agent.agent_tools import build_default_registry


def _headers_for(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}


def test_agent_permission_granted_to_viewer():
    assert role_has_permission(UserRole.VIEWER.value, Permission.AGENT_USE)
    assert role_has_permission(UserRole.OPERATOR.value, Permission.AGENT_USE)


def test_registry_rejects_non_readonly_tools():
    registry = AgentToolRegistry()
    try:
        registry.register(
            AgentToolDefinition(
                name="delete_document",
                description="bad",
                category="documents",
                required_permission=Permission.DOCUMENTS_WRITE,
                read_only=False,
                handler=lambda: None,
            )
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_agent_unsupported_and_sql_plan(client):
    unsupported = client.post(
        "/api/v1/agent/ask",
        json={"question": "Please hack the database and drop all tables"},
    )
    assert unsupported.status_code == 200
    body = unsupported.json()
    assert body["status"] == "unsupported"
    assert body["conversation_id"]
    assert body["steps"] == []

    sqlish = client.post(
        "/api/v1/agent/ask",
        json={"question": "How many invoices do we have?"},
    )
    assert sqlish.status_code == 200
    sql_body = sqlish.json()
    assert sql_body["status"] in {"completed", "partial", "failed"}
    assert "execute_safe_sql_question" in sql_body["tools_used"]
    assert sql_body["steps"]


def test_agent_unusual_invoices_plan(client):
    response = client.post(
        "/api/v1/agent/ask",
        json={"question": "Find unusual invoices.", "max_steps": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"completed", "partial", "failed"}
    assert "get_anomaly_summary" in body["tools_used"]
    assert len(body["steps"]) <= 3


def test_agent_invoice_review_flow(client):
    # Upload + create invoice row for deterministic planner path
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("inv1827.pdf", io.BytesIO(b"%PDF-1.4 invoice INV-1827"), "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    db = client.testing_session_local()
    try:
        invoice = Invoice(
            document_id=uuid.UUID(document_id),
            invoice_number="INV-1827",
            vendor_name="Acme Vendor",
            total_amount=1200,
            currency="USD",
        )
        db.add(invoice)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/agent/ask",
        json={"question": "Why is invoice INV-1827 in review?", "max_steps": 8},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"completed", "partial", "failed"}
    assert "get_invoice" in body["tools_used"]
    assert any(step["tool_name"] == "get_review" for step in body["steps"])

    runs = client.get("/api/v1/agent/runs").json()
    assert runs["total"] >= 1


def test_agent_max_steps_hard_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_HARD_MAX_STEPS", 10)
    monkeypatch.setattr(settings, "AGENT_MAX_STEPS", 8)
    response = client.post(
        "/api/v1/agent/ask",
        json={"question": "Find unusual invoices.", "max_steps": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["steps"]) <= 10

    rejected = client.post(
        "/api/v1/agent/ask",
        json={"question": "Find unusual invoices.", "max_steps": 11},
    )
    assert rejected.status_code == 422


def test_agent_unauthenticated_rejected():
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app

    bare = TestClient(fastapi_app)
    assert bare.post("/api/v1/agent/ask", json={"question": "How many invoices do we have?"}).status_code == 401


def test_agent_audit_has_no_secrets(client):
    client.post("/api/v1/agent/ask", json={"question": "How many invoices do we have?"})
    db = client.testing_session_local()
    try:
        rows = list(db.scalars(select(AuditLog).where(AuditLog.action.like("agent_%"))).all())
        assert rows
        for row in rows:
            blob = (row.details or "").lower()
            assert "password" not in blob
            assert "bearer " not in blob
            assert "jwt" not in blob
    finally:
        db.close()


def test_planner_does_not_guess(client):
    db = client.testing_session_local()
    try:
        plan = DeterministicAgentPlanner(db).plan("Teleport me to the moon using admin rights")
        assert plan.status == "unsupported"
        assert plan.steps == []
    finally:
        db.close()


def test_extract_invoice_number_ignores_investigate_words():
    from app.services.agent.agent_planner import _extract_invoice_number

    assert _extract_invoice_number("Investigate why invoice INV-1827 needs attention") == "INV-1827"
    assert _extract_invoice_number(
        "Investigate why invoice INV-1827 needs attention and summarize the findings."
    ) == "INV-1827"
    assert _extract_invoice_number("Why does invoice INV-1827 need attention?") == "INV-1827"
    assert _extract_invoice_number("Investigate invoice INV-1827") == "INV-1827"
    assert _extract_invoice_number("Investigate invoice INV/2026/001") == "INV/2026/001"
    assert _extract_invoice_number("Look at INV-1001 please") == "INV-1001"

    # Must never peel substrings from English words.
    assert _extract_invoice_number("Investigate the review queue") is None
    assert _extract_invoice_number("Start an investigation now") is None
    assert _extract_invoice_number("invoice totals by vendor") is None
    assert _extract_invoice_number("investigate") != "estigate"
    assert _extract_invoice_number("investigate") is None


def test_planner_investigate_attention_uses_investigation_agent(client):
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("inv1827.pdf", io.BytesIO(b"%PDF-1.4 invoice INV-1827"), "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    db = client.testing_session_local()
    try:
        db.add(
            Invoice(
                document_id=uuid.UUID(document_id),
                invoice_number="INV-1827",
                vendor_name="Acme Vendor",
                total_amount=1200,
                currency="USD",
            )
        )
        db.commit()

        planner = DeterministicAgentPlanner(db)
        cases = [
            "Investigate why invoice INV-1827 needs attention",
            "Investigate why invoice INV-1827 needs attention and summarize the findings.",
            "Why does invoice INV-1827 need attention?",
        ]
        for question in cases:
            plan = planner.plan(question)
            assert plan.status == "ready", question
            assert plan.resolved.get("invoice_number") == "INV-1827", question
            assert "matching 'estigate'" not in (plan.explanation or "").lower()
            tool_names = [step.tool_name for step in plan.steps]
            assert "run_investigation" in tool_names, question
            assert tool_names != []

        investigate_only = planner.plan("Investigate invoice INV-1827")
        assert investigate_only.status == "ready"
        assert investigate_only.resolved.get("invoice_number") == "INV-1827"
        assert investigate_only.intent == "invoice_investigation"
        assert any(step.tool_name == "get_invoice" for step in investigate_only.steps)
    finally:
        db.close()


def test_agent_investigate_attention_api_flow(client):
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("inv1827b.pdf", io.BytesIO(b"%PDF-1.4 invoice INV-1827"), "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    db = client.testing_session_local()
    try:
        db.add(
            Invoice(
                document_id=uuid.UUID(document_id),
                invoice_number="INV-1827",
                vendor_name="Acme Vendor",
                total_amount=1200,
                currency="USD",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/agent/ask",
        json={
            "question": "Investigate why invoice INV-1827 needs attention and summarize the findings.",
            "max_steps": 8,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"completed", "partial", "failed"}
    assert body["status"] != "unsupported"
    assert "estigate" not in (body.get("answer") or "").lower()
    assert "estigate" not in (body.get("summary") or "").lower()
    assert "run_investigation" in body["tools_used"]
    assert body["steps"]


def test_default_registry_tools_are_readonly(client):
    db = client.testing_session_local()
    try:
        registry = build_default_registry(db)
        assert "get_document" in registry.names()
        assert "execute_safe_sql_question" in registry.names()
        assert "delete_document" not in registry.names()
        for tool in registry.list_tools():
            assert tool.read_only is True
            assert tool.handler is not None
    finally:
        db.close()


def test_planner_routes_natural_questions_to_investigation(client):
    db = client.testing_session_local()
    try:
        planner = DeterministicAgentPlanner(db)
        for question in (
            "Which invoices need review and why?",
            "Why does vendor ABC Pvt Ltd have issues?",
        ):
            plan = planner.plan(question)
            assert plan.status == "ready", question
            assert plan.intent == "general_investigation", question
            assert plan.steps[0].tool_name == "run_investigation"
        # Counts and per-vendor totals still go to the SQL tool.
        assert planner.plan("How many invoices do we have?").intent == "safe_sql"
        assert planner.plan("Show invoice totals by vendor").intent == "safe_sql"
        assert planner.plan("Teleport me to the moon").status == "unsupported"
    finally:
        db.close()
