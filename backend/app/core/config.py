from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Known insecure defaults — rejected when APP_ENV=production
_INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "change-me-in-production-docflow-jwt-secret",
        "dev-docflow-jwt-secret-change-me",
        "test-jwt-secret-do-not-use-elsewhere",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Document Workflow Automation"
    APP_ENV: str = "development"
    DEBUG: bool = False
    ENABLE_DOCS: bool | None = None
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/docflow"
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174"
    )
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 25
    TESSERACT_CMD: str = ""
    OCR_LANGUAGE: str = "eng"
    PDF_TEXT_MIN_CHARS: int = 40
    VALIDATION_AMOUNT_TOLERANCE: float = 0.01
    QUANTITY_MATCH_TOLERANCE: float = 0.01
    # When True, process/retry run inline (useful for tests). When False, FastAPI BackgroundTasks.
    DOCUMENT_PROCESSING_SYNC: bool = False

    AUTH_JWT_SECRET: str = "change-me-in-production-docflow-jwt-secret"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    AUTH_BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    AUTH_BOOTSTRAP_ADMIN_EMAIL: str = "admin@example.com"
    AUTH_BOOTSTRAP_ADMIN_PASSWORD: str = ""
    INGESTION_MAX_BATCH_FILES: int = 20
    AGENT_MAX_STEPS: int = 8
    AGENT_MAX_QUESTION_LENGTH: int = 1000
    AGENT_HARD_MAX_STEPS: int = 10

    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 150
    RAG_TOP_K: int = 5
    RAG_MIN_SIMILARITY: float = 0.35
    EMBEDDING_PROVIDER: str = "sentence_transformers"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    LLM_PROVIDER: str = "extractive"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_API_BASE: str = ""

    SQL_GENERATOR_PROVIDER: str = "deterministic"
    SQL_MAX_ROWS: int = 100
    SQL_MAX_QUERY_LENGTH: int = 5000
    SQL_MAX_QUESTION_LENGTH: int = 1000
    SQL_QUERY_TIMEOUT_SECONDS: int = 10

    WORKFLOW_CONFIDENCE_THRESHOLD: float = 0.7
    WORKFLOW_MAX_DEPTH: int = 2
    WORKFLOW_DEDUP_ENABLED: bool = True

    ANOMALY_MODEL_NAME: str = "isolation_forest"
    ANOMALY_MODEL_VERSION: str = "1.0.0"
    ANOMALY_MIN_TRAINING_SAMPLES: int = 10
    ANOMALY_CONTAMINATION: float = 0.1
    ANOMALY_RANDOM_STATE: int = 42
    ANOMALY_N_ESTIMATORS: int = 100
    ANOMALY_NORMAL_MAX: float = 0.35
    ANOMALY_UNUSUAL_MAX: float = 0.55
    ANOMALY_ANOMALY_MAX: float = 0.75
    ANOMALY_MODEL_DIR: str = "storage/anomaly_models"

    DUPLICATE_SIMILARITY_THRESHOLD: float = 0.85
    DUPLICATE_BUSINESS_AMOUNT_TOLERANCE: float = 0.01
    DUPLICATE_MAX_SIMILARITY_CANDIDATES: int = 50
    # Run duplicate detection automatically after each document is processed
    DUPLICATE_AUTO_CHECK_ENABLED: bool = True

    CLASSIFICATION_MODEL_DIR: str = "storage/models"
    CLASSIFICATION_MODEL_VERSION: str = "1.3.0"
    CLASSIFICATION_RANDOM_STATE: int = 42

    # --- Step 26 security / limits ---
    ENABLE_HSTS: bool = False
    HSTS_MAX_AGE_SECONDS: int = 31536000
    MAX_REQUEST_BODY_MB: int = 30
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 20
    RATE_LIMIT_UPLOAD_PER_MINUTE: int = 60
    RATE_LIMIT_AI_PER_MINUTE: int = 30
    AUTH_PASSWORD_MIN_LENGTH: int = 8
    AUTH_PASSWORD_REQUIRE_LETTER: bool = True
    AUTH_PASSWORD_REQUIRE_DIGIT: bool = True
    AUTH_PASSWORD_REQUIRE_SPECIAL: bool = False
    AUTH_LOGIN_MAX_FAILURES: int = 8
    AUTH_LOGIN_LOCKOUT_SECONDS: int = 300

    # --- Step 27 workers / email ---
    PROCESSING_WORKER_MODE: str = "local"  # local | celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_TASK_MAX_RETRIES: int = 3
    CELERY_TASK_RETRY_DELAY_SECONDS: int = 30
    EMAIL_PROVIDER: str = "none"  # none | mock | imap
    EMAIL_IMAP_HOST: str = ""
    EMAIL_IMAP_PORT: int = 993
    EMAIL_IMAP_USERNAME: str = ""
    EMAIL_IMAP_PASSWORD: str = ""
    EMAIL_IMAP_FOLDER: str = "INBOX"
    EMAIL_IMAP_USE_SSL: bool = True
    EMAIL_POLL_INTERVAL_SECONDS: int = 300

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() == "production"

    @property
    def is_development(self) -> bool:
        return not self.is_production

    @property
    def docs_enabled(self) -> bool:
        if self.ENABLE_DOCS is not None:
            return self.ENABLE_DOCS
        return self.is_development

    @property
    def hsts_enabled(self) -> bool:
        return bool(self.ENABLE_HSTS) and self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def upload_dir_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def anomaly_model_dir_path(self) -> Path:
        path = Path(self.ANOMALY_MODEL_DIR)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def classification_model_dir_path(self) -> Path:
        path = Path(self.CLASSIFICATION_MODEL_DIR)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def max_request_body_bytes(self) -> int:
        return self.MAX_REQUEST_BODY_MB * 1024 * 1024

    @property
    def processing_worker_mode(self) -> str:
        mode = (self.PROCESSING_WORKER_MODE or "local").strip().lower()
        if mode not in {"local", "celery"}:
            return "local"
        return mode

    @property
    def uses_celery_workers(self) -> bool:
        return self.processing_worker_mode == "celery"

    @property
    def email_provider_name(self) -> str:
        return (self.EMAIL_PROVIDER or "none").strip().lower()

    @property
    def email_imap_configured(self) -> bool:
        return bool(
            self.email_provider_name == "imap"
            and (self.EMAIL_IMAP_HOST or "").strip()
            and (self.EMAIL_IMAP_USERNAME or "").strip()
            and (self.EMAIL_IMAP_PASSWORD or "").strip()
        )

    def validate_runtime_secrets(self) -> None:
        """Raise ValueError when production secrets are missing or insecure."""
        errors = validate_production_settings(self)
        if errors:
            raise ValueError("; ".join(errors))

    @model_validator(mode="after")
    def _apply_env_defaults(self) -> "Settings":
        if self.is_production and self.DEBUG:
            # Production must not run with debug toggled on via misconfiguration.
            object.__setattr__(self, "DEBUG", False)
        return self


def validate_production_settings(config: Settings | None = None) -> list[str]:
    """Return a list of production configuration problems (empty if OK).

    Safe to call from tests without mutating global settings.
    """
    cfg = config or settings
    if not cfg.is_production:
        return []

    errors: list[str] = []
    secret = (cfg.AUTH_JWT_SECRET or "").strip()
    if secret in _INSECURE_JWT_SECRETS or len(secret) < 32:
        errors.append(
            "AUTH_JWT_SECRET must be set to a strong unique value "
            "(at least 32 characters) when APP_ENV=production"
        )
    if not (cfg.DATABASE_URL or "").strip():
        errors.append("DATABASE_URL is required when APP_ENV=production")
    if not cfg.cors_origin_list:
        errors.append(
            "CORS_ORIGINS must list explicit frontend origins when APP_ENV=production "
            "(wildcard '*' is not allowed with credentials)"
        )
    if any(origin.strip() == "*" for origin in cfg.cors_origin_list):
        errors.append("CORS_ORIGINS must not use '*' when credentials are enabled")
    return errors


settings = Settings()
