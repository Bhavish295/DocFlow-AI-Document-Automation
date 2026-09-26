"""Similarity helpers for duplicate detection (reuse RAG embeddings when available)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.rag_indexing import cosine_similarity


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "") if token}


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union == 0:
        return 0.0
    return intersection / union


def average_embedding(vectors: list[list[float]]) -> list[float] | None:
    usable = [vector for vector in vectors if vector]
    if not usable:
        return None
    dim = len(usable[0])
    if any(len(vector) != dim for vector in usable):
        return None
    totals = [0.0] * dim
    for vector in usable:
        for index, value in enumerate(vector):
            totals[index] += float(value)
    count = float(len(usable))
    return [value / count for value in totals]


def document_embedding(db: Session, document_id: Any) -> list[float] | None:
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
    ).all()
    vectors: list[list[float]] = []
    for chunk in chunks:
        embedding = chunk.embedding
        if embedding is None:
            continue
        if isinstance(embedding, list):
            vectors.append([float(value) for value in embedding])
    return average_embedding(vectors)


def similarity_between_documents(
    db: Session,
    left: Document,
    right: Document,
) -> tuple[float, str]:
    """
    Return (similarity, method).

    Prefer averaged RAG chunk embeddings; fall back to deterministic Jaccard on extracted text.
    """
    left_embedding = document_embedding(db, left.id)
    right_embedding = document_embedding(db, right.id)
    if left_embedding is not None and right_embedding is not None:
        score = cosine_similarity(left_embedding, right_embedding)
        return round(float(score), 4), "embedding_cosine"

    left_text = (left.extracted_text or "").strip()
    right_text = (right.extracted_text or "").strip()
    if left_text and right_text:
        score = jaccard_similarity(left_text, right_text)
        return round(float(score), 4), "text_jaccard"

    return 0.0, "unavailable"


def passes_similarity_threshold(score: float, threshold: float | None = None) -> bool:
    limit = threshold if threshold is not None else settings.DUPLICATE_SIMILARITY_THRESHOLD
    return score >= float(limit)
