import io
import uuid
from pathlib import Path

from PIL import Image

from app.services.text_extraction import TextExtractionError


def _upload_bytes(client, filename: str, content: bytes, content_type: str):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def _upload_pdf(client, filename: str = "invoice.pdf", content: bytes = b"%PDF-1.4 test file"):
    return _upload_bytes(client, filename, content, "application/pdf")


def _make_png_bytes(color=(30, 90, 60)) -> bytes:
    image = Image.new("RGB", (120, 40), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_process_normal_text_pdf(client, monkeypatch):
    created = _upload_pdf(client).json()

    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "Invoice number 1001\nTotal due: 250.00\nCustomer: Acme Corp",
    )

    response = client.post(f"/api/v1/documents/{created['id']}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["processed_at"] is not None
    assert payload["processing_error"] is None


def test_process_image_with_ocr(client, monkeypatch):
    created = _upload_bytes(
        client,
        "receipt.png",
        _make_png_bytes(),
        "image/png",
    ).json()

    monkeypatch.setattr(
        "app.services.text_extraction.ocr_image_file",
        lambda _path: "Store Total 42.50 Thank you",
    )

    response = client.post(f"/api/v1/documents/{created['id']}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["file_type"] == "png"


def test_process_scanned_pdf_uses_ocr(client, monkeypatch):
    created = _upload_pdf(client, filename="scan.pdf").json()

    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "short",
    )
    monkeypatch.setattr(
        "app.services.text_extraction.ocr_pdf_pages",
        lambda _path: "--- Page 1 ---\nScanned invoice line item",
    )

    response = client.post(f"/api/v1/documents/{created['id']}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"

    text_response = client.get(f"/api/v1/documents/{created['id']}/text")
    assert text_response.status_code == 200
    assert "Scanned invoice line item" in text_response.json()["extracted_text"]


def test_get_extracted_text(client, monkeypatch):
    created = _upload_pdf(client).json()
    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "Readable document body for verification purposes.",
    )
    client.post(f"/api/v1/documents/{created['id']}/process")

    response = client.get(f"/api/v1/documents/{created['id']}/text")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert payload["status"] == "processed"
    assert "Readable document body" in payload["extracted_text"]
    assert payload["processing_error"] is None


def test_process_unsupported_file_type(client):
    created = _upload_bytes(
        client,
        "vendors.csv",
        b"name,amount\nAcme,10\n",
        "text/csv",
    ).json()

    response = client.post(f"/api/v1/documents/{created['id']}/process")

    assert response.status_code == 400
    assert "only supported" in response.json()["detail"].lower()
    detail = client.get(f"/api/v1/documents/{created['id']}").json()
    assert detail["status"] == "uploaded"


def test_process_extraction_failure(client, monkeypatch):
    created = _upload_pdf(client).json()

    def _fail(_path):
        raise TextExtractionError("OCR engine unavailable")

    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        _fail,
    )

    response = client.post(f"/api/v1/documents/{created['id']}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert "OCR engine unavailable" in payload["processing_error"]

    text_response = client.get(f"/api/v1/documents/{created['id']}/text")
    assert text_response.status_code == 200
    assert text_response.json()["extracted_text"] is None
    assert text_response.json()["status"] == "failed"


def test_process_nonexistent_document_returns_404(client):
    missing_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{missing_id}/process")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_processing_flags_exact_duplicate_automatically(client, monkeypatch):
    content = b"%PDF-1.4 identical invoice bytes"
    first = _upload_pdf(client, "invoice-a.pdf", content).json()
    second = _upload_pdf(client, "invoice-a-copy.pdf", content).json()

    monkeypatch.setattr(
        "app.services.text_extraction.extract_selectable_pdf_text",
        lambda _path: "Invoice number 1001\nTotal due: 250.00\nCustomer: Acme Corp",
    )

    assert client.post(f"/api/v1/documents/{first['id']}/process").status_code == 200
    assert client.post(f"/api/v1/documents/{second['id']}/process").status_code == 200

    duplicates = client.get(f"/api/v1/duplicates/{second['id']}").json()
    exact = [item for item in duplicates["items"] if item["detection_type"] == "exact_duplicate"]
    assert exact, duplicates
    assert first["id"] in {exact[0]["source_document_id"], exact[0]["duplicate_document_id"]}
    # Document API exposes the count so the UI can show the "Possible Duplicate" badge.
    assert client.get(f"/api/v1/documents/{second['id']}").json()["duplicate_count"] >= 1


def test_ocr_preprocessing_upscales_small_images():
    from app.services.text_extraction import OCR_MIN_WIDTH, preprocess_for_ocr

    small = Image.new("RGB", (900, 460), color=(255, 255, 255))
    prepared = preprocess_for_ocr(small)
    assert prepared.mode == "L"
    assert prepared.width >= OCR_MIN_WIDTH

    large = Image.new("RGB", (2400, 1200), color=(255, 255, 255))
    assert preprocess_for_ocr(large).width == 2400
