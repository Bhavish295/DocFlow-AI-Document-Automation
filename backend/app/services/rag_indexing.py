from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.rag import DocumentIndexStatusResponse, DocumentIndexResponse
from app.services.document_chunking import TextChunker, get_default_chunker
from app.services.embeddings import EmbeddingProvider, get_default_embedding_provider


logger = logging.getLogger(__name__)


def _safe_index_error_message(exc: BaseException) -> str:
    if isinstance(exc, AppError):
        return exc.message
    text = str(exc).strip()
    if not text:
        return "RAG indexing failed."
    # Keep API/UI messages short and avoid dumping raw SQL / paths.
    if len(text) > 300:
        return text[:297] + "..."
    return text


class RagIndexingService:
    def __init__(
        self,
        db: Session,
        chunker: TextChunker | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.chunker = chunker or get_default_chunker()
        self.embedding_provider = embedding_provider or get_default_embedding_provider()

    def index_document(self, document_id: uuid.UUID) -> DocumentIndexResponse:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        extracted = (document.extracted_text or "").strip()
        if not extracted:
            document.rag_index_status = "not_indexed"
            document.rag_index_error = "Document has no extracted text and cannot be indexed."
            document.rag_indexed_at = None
            self.db.commit()
            return DocumentIndexResponse(
                document_id=document.id,
                chunks_created=0,
                status="not_indexed",
                detail=document.rag_index_error,
            )

        try:
            chunks = self.chunker.chunk_text(extracted)
            if not chunks:
                document.rag_index_status = "not_indexed"
                document.rag_index_error = "No usable text chunks could be created."
                document.rag_indexed_at = None
                self.db.commit()
                return DocumentIndexResponse(
                    document_id=document.id,
                    chunks_created=0,
                    status="not_indexed",
                    detail=document.rag_index_error,
                )

            embeddings = self.embedding_provider.embed_texts([chunk.content for chunk in chunks])
            if len(embeddings) != len(chunks):
                raise AppError(
                    "Embedding generation returned an unexpected number of vectors.",
                    status_code=500,
                )

            self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))

            now = datetime.now(timezone.utc)
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                self.db.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        embedding=embedding,
                        character_count=chunk.character_count,
                        created_at=now,
                    )
                )

            document.rag_index_status = "indexed"
            document.rag_index_error = None
            document.rag_indexed_at = now
            self.db.commit()
            return DocumentIndexResponse(
                document_id=document.id,
                chunks_created=len(chunks),
                status="indexed",
                detail=None,
            )
        except AppError as exc:
            logger.exception("RAG indexing failed for document %s: %s", document_id, exc.message)
            self.db.rollback()
            document = self.db.get(Document, document_id)
            if document is not None:
                document.rag_index_status = "failed"
                document.rag_index_error = exc.message
                self.db.commit()
            raise
        except Exception as exc:
            logger.exception("RAG indexing failed for document %s", document_id)
            self.db.rollback()
            document = self.db.get(Document, document_id)
            message = _safe_index_error_message(exc)
            if document is not None:
                document.rag_index_status = "failed"
                document.rag_index_error = message
                self.db.commit()
            raise AppError(message, status_code=500) from exc

    def safe_index_document(self, document_id: uuid.UUID) -> DocumentIndexResponse | None:
        try:
            return self.index_document(document_id)
        except Exception as exc:
            logger.exception("Safe RAG indexing failed for document %s", document_id)
            document = self.db.get(Document, document_id)
            if document is not None:
                document.rag_index_status = "failed"
                document.rag_index_error = _safe_index_error_message(exc)
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()
            return None

    def get_index_status(self, document_id: uuid.UUID) -> DocumentIndexStatusResponse:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        chunk_count = (
            self.db.scalar(
                select(func.count()).select_from(DocumentChunk).where(
                    DocumentChunk.document_id == document.id
                )
            )
            or 0
        )
        status = document.rag_index_status or ("indexed" if chunk_count else "not_indexed")
        return DocumentIndexStatusResponse(
            document_id=document.id,
            status=status,
            indexed=status == "indexed" and chunk_count > 0,
            chunk_count=chunk_count,
            last_indexed_at=document.rag_indexed_at,
            error=document.rag_index_error,
        )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
