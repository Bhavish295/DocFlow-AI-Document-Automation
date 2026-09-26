"""Audit log list API tests."""

from app.core.security import create_access_token
from app.models.user import UserRole


def _headers_for(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}


def test_audit_logs_admin_can_list(client):
    # Login creates audit events
    client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": client.admin_password},
    )
    response = client.get("/api/v1/audit-logs")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert body["total"] >= 1
    assert "password" not in response.text.lower()
    assert "bearer " not in response.text.lower()


def test_audit_logs_viewer_forbidden(client, auth_client_factory):
    viewer = auth_client_factory(
        username="audit_viewer",
        email="audit_viewer@example.com",
        password="ViewerPass1!",
        role=UserRole.VIEWER.value,
    )
    response = client.get("/api/v1/audit-logs", headers=_headers_for(viewer.user))
    assert response.status_code == 403
