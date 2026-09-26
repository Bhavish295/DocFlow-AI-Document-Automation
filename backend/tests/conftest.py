import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app as fastapi_app
from app.models.user import User, UserRole
from app.services.embeddings import get_default_embedding_provider
from app.services import embeddings as embeddings_module
from app.services import rag_indexing as rag_indexing_module
from app.services import rag_retrieval as rag_retrieval_module
from app.services import rag_answer as rag_answer_module
from datetime import datetime, timezone


class DeterministicEmbeddingProvider:
    """Deterministic non-random embeddings for tests only."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            values = [0.0] * self.dimension
            tokens = (text or "").lower().split()
            if not tokens:
                values[0] = 1.0
            else:
                for token in tokens:
                    bucket = abs(hash(token)) % self.dimension
                    values[bucket] += 1.0
                norm = sum(item * item for item in values) ** 0.5 or 1.0
                values = [item / norm for item in values]
            vectors.append(values)
        return vectors


def _create_user(session, *, username: str, email: str, password: str, role: str) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def client(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    model_dir = tmp_path / "classification_models"
    model_dir.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(settings, "CLASSIFICATION_MODEL_DIR", str(model_dir))
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 384)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.1)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "extractive")
    monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_SYNC", True)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "AUTH_JWT_SECRET", "test-jwt-secret-do-not-use-elsewhere")
    monkeypatch.setattr(settings, "AUTH_BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_PER_MINUTE", 1000)
    monkeypatch.setattr(settings, "RATE_LIMIT_UPLOAD_PER_MINUTE", 1000)
    monkeypatch.setattr(settings, "RATE_LIMIT_AI_PER_MINUTE", 1000)
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FAILURES", 100)
    monkeypatch.setattr(settings, "ENABLE_HSTS", False)
    monkeypatch.setattr(settings, "PROCESSING_WORKER_MODE", "local")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "none")

    from app.core.login_protection import login_failure_tracker
    from app.core.rate_limit import rate_limiter

    rate_limiter.reset()
    login_failure_tracker.reset()

    from app.services.ml_classification import reset_default_ml_classifier

    reset_default_ml_classifier()

    provider = DeterministicEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    monkeypatch.setattr(embeddings_module, "get_default_embedding_provider", lambda: provider)
    monkeypatch.setattr(rag_indexing_module, "get_default_embedding_provider", lambda: provider)
    monkeypatch.setattr(rag_retrieval_module, "get_default_embedding_provider", lambda: provider)
    monkeypatch.setattr(rag_answer_module, "get_default_embedding_provider", lambda: provider)
    get_default_embedding_provider.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.main.SessionLocal", TestingSessionLocal)

    seed_db = TestingSessionLocal()
    admin = _create_user(
        seed_db,
        username="admin",
        email="admin@example.com",
        password="AdminPass123!",
        role=UserRole.ADMIN.value,
    )
    seed_db.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    with TestClient(fastapi_app) as test_client:
        token = create_access_token(subject=admin.id, role=admin.role)
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        test_client.testing_session_local = TestingSessionLocal
        test_client.embedding_provider = provider
        test_client.admin_user = admin
        test_client.admin_password = "AdminPass123!"
        yield test_client

    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    get_default_embedding_provider.cache_clear()
    from app.services.ml_classification import reset_default_ml_classifier

    reset_default_ml_classifier()


@pytest.fixture()
def auth_client_factory(client):
    """Create role users in the shared test DB (use with Authorization headers)."""

    class RoleUser:
        def __init__(self, user):
            self.user = user

    def factory(*, username: str, email: str, password: str, role: str):
        db = client.testing_session_local()
        try:
            user = _create_user(db, username=username, email=email, password=password, role=role)
        finally:
            db.close()
        return RoleUser(user)

    return factory
