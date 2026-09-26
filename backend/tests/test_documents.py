import io
import uuid
from pathlib import Path

from app.core.config import settings


def _upload_pdf(client, filename: str = "invoice.pdf", content: bytes = b"%PDF-1.4 test"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def test_upload_supported_file(client):
    response = _upload_pdf(client)

    assert response.status_code == 201
    payload = response.json()
    assert payload["original_filename"] == "invoice.pdf"
    assert payload["file_type"] == "pdf"
    assert payload["status"] == "uploaded"
    assert payload["file_size"] > 0
    assert Path(payload["stored_filename"]).suffix == ".pdf"


def test_reject_unsupported_file(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("malware.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_list_documents(client):
    _upload_pdf(client, filename="one.pdf")
    _upload_pdf(client, filename="two.pdf", content=b"%PDF-1.4 second")

    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert len(payload["items"]) == 2
    assert {item["original_filename"] for item in payload["items"]} == {"one.pdf", "two.pdf"}


def test_get_single_document(client):
    created = _upload_pdf(client).json()

    response = client.get(f"/api/v1/documents/{created['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert payload["original_filename"] == "invoice.pdf"


def test_delete_document(client):
    created = _upload_pdf(client).json()
    document_id = created["id"]
    stored_path = settings.upload_dir_path / created["stored_filename"]

    assert stored_path.exists()
    assert client.get("/api/v1/documents").json()["total"] == 1

    response = client.delete(f"/api/v1/documents/{document_id}")

    assert response.status_code == 200
    assert "deleted" in response.json()["detail"].lower()
    assert client.get("/api/v1/documents").json()["total"] == 0
    assert not stored_path.exists()


def test_get_nonexistent_document_returns_404(client):
    missing_id = uuid.uuid4()
    response = client.get(f"/api/v1/documents/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."
