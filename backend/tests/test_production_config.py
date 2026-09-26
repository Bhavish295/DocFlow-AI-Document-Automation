"""Tests for production configuration, CORS safety, and logging redaction."""

from __future__ import annotations

import logging

from app.core.config import Settings, validate_production_settings
from app.core.logging_config import _RedactFilter, configure_logging
from app.schemas.health import HealthResponse
from app.services.health import get_health_status


def test_get_health_status_shape() -> None:
    status = get_health_status()
    assert isinstance(status, HealthResponse)
    assert status.status == "ok"


def test_validate_production_settings_skips_development() -> None:
    cfg = Settings(
        APP_ENV="development",
        AUTH_JWT_SECRET="change-me-in-production-docflow-jwt-secret",
        DATABASE_URL="postgresql+psycopg2://u:p@localhost/db",
        CORS_ORIGINS="http://localhost:5173",
    )
    assert validate_production_settings(cfg) == []


def test_validate_production_settings_rejects_insecure_jwt() -> None:
    cfg = Settings(
        APP_ENV="production",
        AUTH_JWT_SECRET="change-me-in-production-docflow-jwt-secret",
        DATABASE_URL="postgresql+psycopg2://u:p@localhost/db",
        CORS_ORIGINS="http://localhost:5173",
    )
    errors = validate_production_settings(cfg)
    assert any("AUTH_JWT_SECRET" in item for item in errors)


def test_validate_production_settings_rejects_short_jwt() -> None:
    cfg = Settings(
        APP_ENV="production",
        AUTH_JWT_SECRET="short-secret",
        DATABASE_URL="postgresql+psycopg2://u:p@localhost/db",
        CORS_ORIGINS="http://localhost:5173",
    )
    errors = validate_production_settings(cfg)
    assert any("AUTH_JWT_SECRET" in item for item in errors)


def test_validate_production_settings_rejects_wildcard_cors() -> None:
    cfg = Settings(
        APP_ENV="production",
        AUTH_JWT_SECRET="a" * 32,
        DATABASE_URL="postgresql+psycopg2://u:p@localhost/db",
        CORS_ORIGINS="*",
    )
    errors = validate_production_settings(cfg)
    assert any("CORS" in item or "*" in item for item in errors)


def test_validate_production_settings_rejects_empty_cors() -> None:
    cfg = Settings(
        APP_ENV="production",
        AUTH_JWT_SECRET="a" * 32,
        DATABASE_URL="postgresql+psycopg2://u:p@localhost/db",
        CORS_ORIGINS="  ,  ",
    )
    errors = validate_production_settings(cfg)
    assert any("CORS_ORIGINS" in item for item in errors)


def test_validate_production_settings_accepts_strong_config() -> None:
    cfg = Settings(
        APP_ENV="production",
        AUTH_JWT_SECRET="a" * 32,
        DATABASE_URL="postgresql+psycopg2://u:p@localhost/db",
        CORS_ORIGINS="https://app.example.com",
        DEBUG=True,
    )
    assert cfg.DEBUG is False
    assert validate_production_settings(cfg) == []
    assert cfg.is_production is True
    assert cfg.docs_enabled is False


def test_docs_enabled_override() -> None:
    cfg = Settings(APP_ENV="production", ENABLE_DOCS=True, AUTH_JWT_SECRET="a" * 32)
    assert cfg.docs_enabled is True


def test_cors_origin_list_parsing() -> None:
    cfg = Settings(
        CORS_ORIGINS=" http://localhost:5173 , http://127.0.0.1:5173 ",
    )
    assert cfg.cors_origin_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_log_redaction_filter() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login password=super-secret token=abc123",
        args=(),
        exc_info=None,
    )
    filt = _RedactFilter()
    assert filt.filter(record) is True
    message = record.getMessage()
    assert "super-secret" not in message
    assert "[REDACTED]" in message


def test_configure_logging_runs() -> None:
    configure_logging()
    logging.getLogger("app.test").info("ok")
