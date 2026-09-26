"""Tests for duplicate similarity helpers."""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.duplicate_similarity import (
    jaccard_similarity,
    passes_similarity_threshold,
    similarity_between_documents,
    tokenize,
)
from app.services.rag_indexing import cosine_similarity


def test_tokenize_and_jaccard():
    assert "invoice" in tokenize("Invoice #123 Total Amount")
    similar = jaccard_similarity(
        "Vendor Acme invoice 1001 total 500 USD",
        "Vendor Acme invoice 1001 total 500 USD payment due",
    )
    different = jaccard_similarity(
        "Vendor Acme invoice 1001 total 500 USD",
        "Purchase order for office chairs and desks",
    )
    assert similar > different
    assert similar > 0.5


def test_passes_similarity_threshold(monkeypatch):
    monkeypatch.setattr(settings, "DUPLICATE_SIMILARITY_THRESHOLD", 0.8)
    assert passes_similarity_threshold(0.85) is True
    assert passes_similarity_threshold(0.5) is False
    assert passes_similarity_threshold(0.75, threshold=0.7) is True


def test_text_jaccard_fallback(client):
    db = client.testing_session_local()
    try:
        left = Document(
            original_filename="a.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/a.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            extracted_text="Acme Corp invoice number INV-100 total due 1200 USD",
        )
        right = Document(
            original_filename="b.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/b.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            extracted_text="Acme Corp invoice number INV-100 total due 1200 USD paid",
        )
        db.add_all([left, right])
        db.commit()
        db.refresh(left)
        db.refresh(right)
        score, method = similarity_between_documents(db, left, right)
        assert method == "text_jaccard"
        assert score >= 0.7
    finally:
        db.close()


def test_embedding_cosine_when_chunks_present(client):
    db = client.testing_session_local()
    try:
        left = Document(
            original_filename="e1.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/e1.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            extracted_text="unused when embeddings exist",
        )
        right = Document(
            original_filename="e2.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            file_type="pdf",
            file_size=10,
            storage_path="storage/uploads/e2.pdf",
            status=DocumentStatus.PROCESSED.value,
            document_type="invoice",
            extracted_text="also unused",
        )
        db.add_all([left, right])
        db.flush()
        vector_a = [1.0, 0.0, 0.0]
        vector_b = [0.9, 0.1, 0.0]
        db.add_all(
            [
                DocumentChunk(
                    document_id=left.id,
                    chunk_index=0,
                    content="chunk a",
                    content_hash="a" * 64,
                    embedding=vector_a + [0.0] * (settings.EMBEDDING_DIMENSION - 3),
                    character_count=7,
                ),
                DocumentChunk(
                    document_id=right.id,
                    chunk_index=0,
                    content="chunk b",
                    content_hash="b" * 64,
                    embedding=vector_b + [0.0] * (settings.EMBEDDING_DIMENSION - 3),
                    character_count=7,
                ),
            ]
        )
        db.commit()
        db.refresh(left)
        db.refresh(right)
        score, method = similarity_between_documents(db, left, right)
        assert method == "embedding_cosine"
        expected = cosine_similarity(
            vector_a + [0.0] * (settings.EMBEDDING_DIMENSION - 3),
            vector_b + [0.0] * (settings.EMBEDDING_DIMENSION - 3),
        )
        assert abs(score - round(expected, 4)) < 1e-6
        assert score > 0.9
    finally:
        db.close()
