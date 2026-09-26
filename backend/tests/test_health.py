from app.schemas.health import HealthResponse


def test_health_check(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "service" in payload
    assert payload["version"] == "0.1.0"


def test_readiness_check(client) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["storage"] == "ok"
    body = response.text.lower()
    assert "postgresql" not in body
    assert "password" not in body
    assert isinstance(HealthResponse.model_validate(
        {k: payload[k] for k in ("status", "service", "version")}
    ), HealthResponse)
