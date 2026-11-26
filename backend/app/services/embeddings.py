from __future__ import annotations

from functools import lru_cache
import logging
import threading
from typing import Protocol

from app.core.config import settings
from app.core.exceptions import AppError


logger = logging.getLogger(__name__)

MISSING_EMBEDDING_DEPENDENCY_MESSAGE = (
    "Embedding model is unavailable. Install the required dependency with "
    "`pip install sentence-transformers` (includes torch) and restart the backend."
)


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in order."""


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str | None = None, dimension: int | None = None) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self._model = None
        # Several background processing jobs can index at once; loading the model
        # concurrently from multiple threads fails intermittently, so serialize it.
        self._load_lock = threading.Lock()

    def _load_model(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            return self._load_model_locked()

    def _load_model_locked(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            logger.exception("sentence-transformers import failed")
            raise AppError(MISSING_EMBEDDING_DEPENDENCY_MESSAGE, status_code=500) from exc
        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception as exc:
            logger.exception("Failed to load embedding model %s", self.model_name)
            raise AppError(
                "Embedding model is unavailable. Check EMBEDDING_MODEL, ensure the "
                "model can be downloaded or is cached locally, then restart the backend.",
                status_code=500,
            ) from exc
        return self._model

    def embed_text(self, text: str) -> list[float]:
        vectors = self.embed_texts([text])
        return vectors[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        cleaned = [item if item and item.strip() else " " for item in texts]
        model = self._load_model()
        try:
            vectors = model.encode(cleaned, normalize_embeddings=True)
        except Exception as exc:
            logger.exception("Embedding generation failed")
            raise AppError(
                "Embedding generation failed for the local sentence-transformers model.",
                status_code=500,
            ) from exc
        result: list[list[float]] = []
        for vector in vectors:
            values = [float(item) for item in vector.tolist()]
            if len(values) != self.dimension:
                raise AppError(
                    "Vector storage failed because embedding dimensions do not match "
                    f"the configured vector schema (expected {self.dimension}, got {len(values)}).",
                    status_code=500,
                )
            result.append(values)
        return result


@lru_cache(maxsize=1)
def get_default_embedding_provider() -> EmbeddingProvider:
    provider = (settings.EMBEDDING_PROVIDER or "sentence_transformers").strip().lower()
    if provider in {"sentence_transformers", "local", "default"}:
        return SentenceTransformerEmbeddingProvider()
    raise AppError(
        f"Unsupported EMBEDDING_PROVIDER '{settings.EMBEDDING_PROVIDER}'. "
        "Use 'sentence_transformers' for the local free embedding model.",
        status_code=500,
    )
