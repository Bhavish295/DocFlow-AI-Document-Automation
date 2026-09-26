from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import EmbeddingProvider, get_default_embedding_provider
from app.services.rag_indexing import cosine_similarity


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    document_type: str | None
    content: str
    similarity: float
    chunk_index: int


class RagRetrievalService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.embedding_provider = embedding_provider or get_default_embedding_provider()

    def search_similar_chunks(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_id: uuid.UUID | None = None,
        document_type: str | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievedChunk]:
        cleaned = " ".join((query or "").split()).strip()
        if not cleaned:
            raise AppError("query is required.", status_code=400)

        limit = top_k if top_k is not None else settings.RAG_TOP_K
        if limit < 1 or limit > 50:
            raise AppError("top_k must be between 1 and 50.", status_code=400)

        threshold = (
            min_similarity if min_similarity is not None else settings.RAG_MIN_SIMILARITY
        )
        query_embedding = self.embedding_provider.embed_text(cleaned)

        dialect = self.db.bind.dialect.name if self.db.bind is not None else "sqlite"
        if dialect == "postgresql" and self._pgvector_ready():
            return self._search_pgvector(
                query_embedding,
                top_k=limit,
                document_id=document_id,
                document_type=document_type,
                min_similarity=threshold,
            )
        return self._search_python(
            query_embedding,
            top_k=limit,
            document_id=document_id,
            document_type=document_type,
            min_similarity=threshold,
        )

    def _pgvector_ready(self) -> bool:
        try:
            extension = self.db.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
            if not extension:
                return False
            column_type = self.db.execute(
                text(
                    """
                    SELECT udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'document_chunks' AND column_name = 'embedding'
                    """
                )
            ).scalar()
            return str(column_type or "").lower() == "vector"
        except Exception:
            return False

    def _search_pgvector(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        document_id: uuid.UUID | None,
        document_type: str | None,
        min_similarity: float,
    ) -> list[RetrievedChunk]:
        vector_literal = "[" + ",".join(str(float(item)) for item in query_embedding) + "]"
        filters = ["c.embedding IS NOT NULL"]
        params: dict = {"query_vector": vector_literal, "top_k": top_k}
        if document_id is not None:
            filters.append("c.document_id = :document_id")
            params["document_id"] = str(document_id)
        if document_type:
            filters.append("d.document_type = :document_type")
            params["document_type"] = document_type.strip().lower()

        where_clause = " AND ".join(filters)
        sql = text(
            f"""
            SELECT
                c.id AS chunk_id,
                c.document_id AS document_id,
                d.original_filename AS filename,
                d.document_type AS document_type,
                c.content AS content,
                c.chunk_index AS chunk_index,
                1 - (c.embedding <=> CAST(:query_vector AS vector)) AS similarity
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE {where_clause}
            ORDER BY c.embedding <=> CAST(:query_vector AS vector)
            LIMIT :top_k
            """
        )
        rows = self.db.execute(sql, params).mappings().all()
        results: list[RetrievedChunk] = []
        for row in rows:
            similarity = float(row["similarity"] or 0.0)
            if similarity < min_similarity:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    filename=row["filename"],
                    document_type=row["document_type"],
                    content=row["content"],
                    similarity=round(similarity, 4),
                    chunk_index=row["chunk_index"],
                )
            )
        return results

    def _search_python(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        document_id: uuid.UUID | None,
        document_type: str | None,
        min_similarity: float,
    ) -> list[RetrievedChunk]:
        stmt = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.embedding.is_not(None))
        )
        if document_id is not None:
            stmt = stmt.where(DocumentChunk.document_id == document_id)
        if document_type:
            stmt = stmt.where(Document.document_type == document_type.strip().lower())

        scored: list[RetrievedChunk] = []
        for chunk, document in self.db.execute(stmt).all():
            similarity = cosine_similarity(query_embedding, chunk.embedding or [])
            if similarity < min_similarity:
                continue
            scored.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    filename=document.original_filename,
                    document_type=document.document_type,
                    content=chunk.content,
                    similarity=round(similarity, 4),
                    chunk_index=chunk.chunk_index,
                )
            )
        scored.sort(key=lambda item: item.similarity, reverse=True)
        return scored[:top_k]
