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
