import io
import uuid

from app.core.exceptions import AppError
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.document_chunking import ParagraphAwareChunker, hash_content, normalize_whitespace
from app.services.llm import ExtractiveLLMProvider
from app.services.rag_answer import NO_CONTEXT_ANSWER, RagAnswerService
from app.services.rag_indexing import RagIndexingService, cosine_similarity
from sqlalchemy import func, select, update


SAMPLE_TEXT = """
Payment Terms

Invoices are payable within 30 days of the invoice date.

Late payments may incur a service fee.

Approval Process

Invoices above 100000 require finance manager approval before payment.
"""


def test_normalize_and_chunk_order_overlap():
    chunker = ParagraphAwareChunker(chunk_size=120, overlap=20)
    chunks = chunker.chunk_text(SAMPLE_TEXT)
    assert chunks
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.content.strip() for chunk in chunks)
    assert all(chunk.content_hash == hash_content(chunk.content) for chunk in chunks)
    if len(chunks) > 1:
        assert chunks[0].content != chunks[1].content


def test_empty_text_chunking():
    assert ParagraphAwareChunker().chunk_text("   ") == []
    assert normalize_whitespace(" a \n\n\n b ") == "a \n\n b"


def test_index_reindex_and_status(client):
    created = client.post(
        "/api/v1/documents",
        files={"file": ("policy.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()

    db = client.testing_session_local()
    try:
        db.execute(
            update(Document)
            .where(Document.id == uuid.UUID(created["id"]))
            .values(
                extracted_text=SAMPLE_TEXT,
                status=DocumentStatus.PROCESSED.value,
                document_type="contract",
            )
        )
        db.commit()
    finally:
        db.close()

    indexed = client.post(f"/api/v1/documents/{created['id']}/index")
    assert indexed.status_code == 200
    body = indexed.json()
    assert body["status"] == "indexed"
    assert body["chunks_created"] > 0

    status = client.get(f"/api/v1/documents/{created['id']}/index-status")
    assert status.status_code == 200
    assert status.json()["indexed"] is True
    assert status.json()["chunk_count"] == body["chunks_created"]

    first_count = body["chunks_created"]
    reindexed = client.post(f"/api/v1/documents/{created['id']}/index")
    assert reindexed.status_code == 200
    assert reindexed.json()["chunks_created"] == first_count

    db = client.testing_session_local()
    try:
        count = db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == uuid.UUID(created["id"])
            )
        )
        assert count == first_count
    finally:
        db.close()


def test_index_without_extracted_text(client):
    created = client.post(
        "/api/v1/documents",
        files={"file": ("empty.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    response = client.post(f"/api/v1/documents/{created['id']}/index")
    assert response.status_code == 200
    assert response.json()["status"] == "not_indexed"
    assert "no extracted text" in response.json()["detail"].lower()


def test_search_and_ask_with_filters(client):
    created = client.post(
        "/api/v1/documents",
        files={"file": ("policy.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    db = client.testing_session_local()
    try:
        db.execute(
            update(Document)
            .where(Document.id == uuid.UUID(created["id"]))
            .values(
                extracted_text=SAMPLE_TEXT,
                status=DocumentStatus.PROCESSED.value,
                document_type="contract",
            )
        )
        db.commit()
    finally:
        db.close()

    assert client.post(f"/api/v1/documents/{created['id']}/index").status_code == 200

    search = client.post(
        "/api/v1/rag/search",
        json={"query": "payment terms invoices payable", "top_k": 3, "document_type": "contract"},
    )
    assert search.status_code == 200
    payload = search.json()
    assert payload["query"]
    assert len(payload["results"]) >= 1
    assert payload["results"][0]["document_id"] == created["id"]
    assert "embedding" not in payload["results"][0]

    filtered = client.post(
        "/api/v1/rag/search",
        json={"query": "payment terms", "document_id": created["id"], "top_k": 2},
    )
    assert filtered.status_code == 200
    assert all(item["document_id"] == created["id"] for item in filtered.json()["results"])

    ask = client.post(
        "/api/v1/rag/ask",
        json={"question": "What are the payment terms?"},
    )
    assert ask.status_code == 200
    answer = ask.json()
    assert answer["answer"]
    assert answer["sources"]
    assert answer["sources"][0]["filename"] == "policy.pdf"


def test_no_context_does_not_hallucinate(client):
    response = client.post(
        "/api/v1/rag/ask",
        json={"question": "What is the secret launch code for Mars?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == []
    assert "enough relevant information" in payload["answer"].lower()
    assert payload["answer"] == NO_CONTEXT_ANSWER


def test_processing_continues_if_indexing_fails(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(
        "app.services.rag_indexing.RagIndexingService.index_document",
        boom,
    )

    created = client.post(
        "/api/v1/documents",
        files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "Invoice Number: INV-1\nTotal Amount: 100\nBill To: ACME",
    )
    response = client.post(f"/api/v1/documents/{created['id']}/process")
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    detail = client.get(f"/api/v1/documents/{created['id']}").json()
    assert detail["status"] == "processed"
    assert detail["rag_index_status"] == "failed"
    assert detail.get("rag_index_error")


def test_missing_sentence_transformers_returns_actionable_error(client, monkeypatch):
    from app.services import embeddings as embeddings_module
    from app.services.embeddings import (
        MISSING_EMBEDDING_DEPENDENCY_MESSAGE,
        SentenceTransformerEmbeddingProvider,
    )

    provider = SentenceTransformerEmbeddingProvider(dimension=384)

    def boom(self):
        raise AppError(MISSING_EMBEDDING_DEPENDENCY_MESSAGE, status_code=500)

    monkeypatch.setattr(SentenceTransformerEmbeddingProvider, "_load_model", boom)
    monkeypatch.setattr(embeddings_module, "get_default_embedding_provider", lambda: provider)
    monkeypatch.setattr(
        "app.services.rag_indexing.get_default_embedding_provider",
        lambda: provider,
    )

    created = client.post(
        "/api/v1/documents",
        files={"file": ("policy.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    db = client.testing_session_local()
    try:
        db.execute(
            update(Document)
            .where(Document.id == uuid.UUID(created["id"]))
            .values(
                extracted_text=SAMPLE_TEXT,
                status=DocumentStatus.PROCESSED.value,
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/v1/documents/{created['id']}/index")
    assert response.status_code == 500
    assert "Embedding model is unavailable" in response.json()["detail"]
    assert "sentence-transformers" in response.json()["detail"]

    detail = client.get(f"/api/v1/documents/{created['id']}").json()
    assert detail["status"] == "processed"
    assert detail["rag_index_status"] == "failed"
    assert detail["rag_index_error"] == MISSING_EMBEDDING_DEPENDENCY_MESSAGE


def test_embedding_dimension_consistency(client):
    created = client.post(
        "/api/v1/documents",
        files={"file": ("dims.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},
    ).json()
    db = client.testing_session_local()
    try:
        db.execute(
            update(Document)
            .where(Document.id == uuid.UUID(created["id"]))
            .values(
                extracted_text=SAMPLE_TEXT,
                status=DocumentStatus.PROCESSED.value,
            )
        )
        db.commit()
    finally:
        db.close()

    indexed = client.post(f"/api/v1/documents/{created['id']}/index")
    assert indexed.status_code == 200
    assert indexed.json()["status"] == "indexed"

    db = client.testing_session_local()
    try:
        chunks = db.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(created["id"]))
        ).all()
        assert chunks
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 384
            assert all(isinstance(value, float) for value in chunk.embedding)
    finally:
        db.close()


def test_cosine_and_extractive_llm():
    left = [1.0, 0.0, 0.0]
    right = [1.0, 0.0, 0.0]
    assert cosine_similarity(left, right) == 1.0
    answer = ExtractiveLLMProvider().generate_answer(
        "What is payable?",
        "[Source: policy.pdf]\nInvoices are payable within 30 days.",
        ["policy.pdf"],
    )
    assert "payable within 30 days" in answer.answer


def test_invalid_rag_requests(client):
    assert client.post("/api/v1/rag/search", json={"query": " ", "top_k": 5}).status_code == 400
    assert client.post("/api/v1/rag/ask", json={"question": ""}).status_code == 400
    assert client.post("/api/v1/rag/search", json={"query": "hello", "top_k": 0}).status_code == 422
