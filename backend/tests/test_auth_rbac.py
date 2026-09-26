import io

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.user import UserRole


def _headers_for(user) -> dict:
    token = create_access_token(subject=user.id, role=user.role)
    return {"Authorization": f"Bearer {token}"}


def test_login_and_me(client):
    unauth = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert unauth.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": client.admin_password},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "admin"
    assert "password_hash" not in body["user"]

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    assert "password_hash" not in me.json()


def test_inactive_user_cannot_login(client):
    from datetime import datetime, timezone

    from app.core.security import hash_password
    from app.models.user import User

    db = client.testing_session_local()
    now = datetime.now(timezone.utc)
    user = User(
        username="inactive",
        email="inactive@example.com",
        password_hash=hash_password("InactivePass1!"),
        role=UserRole.VIEWER.value,
        is_active=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.close()

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "inactive", "password": "InactivePass1!"},
    )
    assert response.status_code == 401


def test_password_is_hashed_and_hidden(client):
    created = client.post(
        "/api/v1/users",
        json={
            "username": "operator1",
            "email": "operator1@example.com",
            "password": "OperatorPass1!",
            "role": "operator",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert "password" not in body
    assert "password_hash" not in body

    db = client.testing_session_local()
    from sqlalchemy import select

    from app.models.user import User

    row = db.scalar(select(User).where(User.username == "operator1"))
    assert row is not None
    assert row.password_hash != "OperatorPass1!"
    assert row.password_hash.startswith("$2")
    db.close()


def test_rbac_denials_and_allows(client, auth_client_factory):
    viewer = auth_client_factory(
        username="viewer1",
        email="viewer1@example.com",
        password="ViewerPass1!",
        role="viewer",
    )
    operator = auth_client_factory(
        username="operator2",
        email="operator2@example.com",
        password="OperatorPass2!",
        role="operator",
    )
    reviewer = auth_client_factory(
        username="reviewer1",
        email="reviewer1@example.com",
        password="ReviewerPass1!",
        role="reviewer",
    )

    assert (
        client.post(
            "/api/v1/users",
            headers=_headers_for(viewer.user),
            json={
                "username": "x",
                "email": "x@example.com",
                "password": "Password123!",
                "role": "viewer",
            },
        ).status_code
        == 403
    )
    assert client.get("/api/v1/users", headers=_headers_for(operator.user)).status_code == 403
    assert (
        client.post("/api/v1/classification/train", headers=_headers_for(viewer.user)).status_code
        == 403
    )

    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    ).json()
    assert (
        client.post(
            f"/api/v1/documents/{uploaded['id']}/process",
            headers=_headers_for(viewer.user),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/documents/{uploaded['id']}/process",
            headers=_headers_for(operator.user),
        ).status_code
        == 200
    )

    bare = TestClient(fastapi_app)
    assert bare.get("/api/v1/documents").status_code == 401

    assert (
        client.get("/api/v1/reviews", headers=_headers_for(reviewer.user)).status_code == 200
    )
    assert (
        client.post(
            "/api/v1/reviews/00000000-0000-0000-0000-000000000001/approve",
            headers=_headers_for(viewer.user),
        ).status_code
        == 403
    )


def test_user_management_and_last_admin(client):
    created = client.post(
        "/api/v1/users",
        json={
            "username": "dupuser",
            "email": "dup@example.com",
            "password": "DupPass123!",
            "role": "viewer",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    dup = client.post(
        "/api/v1/users",
        json={
            "username": "dupuser",
            "email": "other@example.com",
            "password": "DupPass123!",
            "role": "viewer",
        },
    )
    assert dup.status_code == 409

    deactivated = client.delete(f"/api/v1/users/{user_id}")
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    admin_id = str(client.admin_user.id)
    assert client.delete(f"/api/v1/users/{admin_id}").status_code == 400


def test_protected_agents_require_auth(client, auth_client_factory):
    bare = TestClient(fastapi_app)
    assert bare.post("/api/v1/sql/ask", json={"question": "how many documents"}).status_code == 401
    assert (
        bare.post("/api/v1/investigations/ask", json={"question": "summarize"}).status_code == 401
    )

    viewer = auth_client_factory(
        username="viewer_sql",
        email="viewer_sql@example.com",
        password="ViewerPass9!",
        role="viewer",
    )
    assert (
        client.post(
            "/api/v1/sql/ask",
            headers=_headers_for(viewer.user),
            json={"question": "how many documents"},
        ).status_code
        == 200
    )
