from datetime import datetime, timedelta, timezone
import io
import uuid

from sqlalchemy import update

from app.models.document import Document, DocumentStatus, DocumentType


def _upload(client, filename: str, content: bytes | None = None):
    payload = content if content is not None else f"%PDF-1.4 {filename}".encode()
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(payload), "application/pdf")},
    ).json()


def _set_document_fields(client, document_id, **fields):
    db = client.testing_session_local()
    try:
        db.execute(update(Document).where(Document.id == uuid.UUID(document_id)).values(**fields))
        db.commit()
    finally:
        db.close()


def test_search_filename_case_insensitive_partial(client):
    _upload(client, "invoice_001.pdf")
    _upload(client, "customer_invoice.pdf")
    _upload(client, "receipt.png", content=b"\x89PNG\r\n\x1a\n" + b"0" * 20)

    response = client.get("/api/v1/documents", params={"search": "InVoIcE"})
    assert response.status_code == 200
    names = {item["original_filename"] for item in response.json()["items"]}
    assert names == {"invoice_001.pdf", "customer_invoice.pdf"}
    assert response.json()["total"] == 2


def test_search_extracted_text_and_document_type(client):
    first = _upload(client, "alpha.pdf")
    second = _upload(client, "beta.pdf")
    _set_document_fields(
        client,
        first["id"],
        extracted_text="Vendor ABC Traders invoice details",
        document_type=DocumentType.INVOICE.value,
        status=DocumentStatus.PROCESSED.value,
    )
    _set_document_fields(
        client,
        second["id"],
        document_type=DocumentType.CONTRACT.value,
        status=DocumentStatus.PROCESSED.value,
    )

    by_text = client.get("/api/v1/documents", params={"search": "abc"})
    assert by_text.status_code == 200
    assert by_text.json()["total"] == 1
    assert by_text.json()["items"][0]["id"] == first["id"]

    by_type_text = client.get("/api/v1/documents", params={"search": "contract"})
    assert by_type_text.json()["total"] == 1
    assert by_type_text.json()["items"][0]["id"] == second["id"]


def test_document_type_and_status_filters(client):
    invoice = _upload(client, "inv.pdf")
    po = _upload(client, "po.pdf")
    contract = _upload(client, "contract.pdf")
    other = _upload(client, "misc.pdf")

    _set_document_fields(
        client,
        invoice["id"],
        document_type=DocumentType.INVOICE.value,
        status=DocumentStatus.PROCESSED.value,
    )
    _set_document_fields(
        client,
        po["id"],
        document_type=DocumentType.PURCHASE_ORDER.value,
        status=DocumentStatus.UPLOADED.value,
    )
    _set_document_fields(
        client,
        contract["id"],
        document_type=DocumentType.CONTRACT.value,
        status=DocumentStatus.FAILED.value,
    )
    _set_document_fields(
        client,
        other["id"],
        document_type=DocumentType.OTHER.value,
        status=DocumentStatus.PROCESSING.value,
    )

    assert client.get("/api/v1/documents", params={"document_type": "invoice"}).json()["total"] == 1
    assert (
        client.get("/api/v1/documents", params={"document_type": "purchase_order"}).json()["total"]
        == 1
    )
    assert client.get("/api/v1/documents", params={"document_type": "contract"}).json()["total"] == 1
    assert client.get("/api/v1/documents", params={"document_type": "other"}).json()["total"] == 1

    assert client.get("/api/v1/documents", params={"status": "uploaded"}).json()["total"] == 1
    assert client.get("/api/v1/documents", params={"status": "processing"}).json()["total"] == 1
    assert client.get("/api/v1/documents", params={"status": "processed"}).json()["total"] == 1
    assert client.get("/api/v1/documents", params={"status": "failed"}).json()["total"] == 1


def test_date_range_inclusive_end(client):
    older = _upload(client, "old.pdf")
    newer = _upload(client, "new.pdf")
    mid = _upload(client, "mid.pdf")

    day = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    _set_document_fields(client, older["id"], uploaded_at=day - timedelta(days=2))
    _set_document_fields(client, mid["id"], uploaded_at=day)
    _set_document_fields(client, newer["id"], uploaded_at=day + timedelta(days=2))

    response = client.get(
        "/api/v1/documents",
        params={"uploaded_from": "2026-03-10", "uploaded_to": "2026-03-10"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == mid["id"]

    spanned = client.get(
        "/api/v1/documents",
        params={"uploaded_from": "2026-03-08", "uploaded_to": "2026-03-12"},
    )
    assert spanned.json()["total"] == 3


def test_sorting_options(client):
    first = _upload(client, "b-file.pdf", content=b"%PDF-1.4 aaa")
    second = _upload(client, "a-file.pdf", content=b"%PDF-1.4 bbbbbbbb")
    third = _upload(client, "c-file.pdf", content=b"%PDF-1.4 cc")

    _set_document_fields(
        client,
        first["id"],
        document_type=DocumentType.INVOICE.value,
        status=DocumentStatus.PROCESSED.value,
        file_size=10,
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    _set_document_fields(
        client,
        second["id"],
        document_type=DocumentType.CONTRACT.value,
        status=DocumentStatus.FAILED.value,
        file_size=30,
        uploaded_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    _set_document_fields(
        client,
        third["id"],
        document_type=DocumentType.OTHER.value,
        status=DocumentStatus.UPLOADED.value,
        file_size=20,
        uploaded_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    newest = client.get(
        "/api/v1/documents",
        params={"sort_by": "uploaded_at", "sort_order": "desc"},
    ).json()["items"]
    assert [item["original_filename"] for item in newest] == [
        "a-file.pdf",
        "c-file.pdf",
        "b-file.pdf",
    ]

    oldest = client.get(
        "/api/v1/documents",
        params={"sort_by": "uploaded_at", "sort_order": "asc"},
    ).json()["items"]
    assert [item["original_filename"] for item in oldest] == [
        "b-file.pdf",
        "c-file.pdf",
        "a-file.pdf",
    ]

    name_asc = client.get(
        "/api/v1/documents",
        params={"sort_by": "filename", "sort_order": "asc"},
    ).json()["items"]
    assert [item["original_filename"] for item in name_asc] == [
        "a-file.pdf",
        "b-file.pdf",
        "c-file.pdf",
    ]

    name_desc = client.get(
        "/api/v1/documents",
        params={"sort_by": "filename", "sort_order": "desc"},
    ).json()["items"]
    assert [item["original_filename"] for item in name_desc] == [
        "c-file.pdf",
        "b-file.pdf",
        "a-file.pdf",
    ]

    by_type = client.get(
        "/api/v1/documents",
        params={"sort_by": "document_type", "sort_order": "asc"},
    ).json()["items"]
    assert [item["document_type"] for item in by_type] == [
        DocumentType.CONTRACT.value,
        DocumentType.INVOICE.value,
        DocumentType.OTHER.value,
    ]

    by_status = client.get(
        "/api/v1/documents",
        params={"sort_by": "status", "sort_order": "asc"},
    ).json()["items"]
    assert [item["status"] for item in by_status] == [
        DocumentStatus.FAILED.value,
        DocumentStatus.PROCESSED.value,
        DocumentStatus.UPLOADED.value,
    ]


def test_pagination_metadata(client):
    for index in range(5):
        _upload(client, f"doc-{index}.pdf", content=f"%PDF-1.4 {index}".encode())

    page1 = client.get("/api/v1/documents", params={"page": 1, "page_size": 2}).json()
    assert page1["total"] == 5
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert page1["total_pages"] == 3
    assert page1["has_next"] is True
    assert page1["has_previous"] is False
    assert len(page1["items"]) == 2

    page2 = client.get("/api/v1/documents", params={"page": 2, "page_size": 2}).json()
    assert page2["has_next"] is True
    assert page2["has_previous"] is True
    assert len(page2["items"]) == 2

    page3 = client.get("/api/v1/documents", params={"page": 3, "page_size": 2}).json()
    assert page3["has_next"] is False
    assert page3["has_previous"] is True
    assert len(page3["items"]) == 1

    empty = client.get(
        "/api/v1/documents",
        params={"search": "does-not-exist", "page": 1, "page_size": 20},
    ).json()
    assert empty["total"] == 0
    assert empty["total_pages"] == 0
    assert empty["has_next"] is False
    assert empty["has_previous"] is False
    assert empty["items"] == []


def test_validation_errors(client):
    assert client.get("/api/v1/documents", params={"page": 0}).status_code == 422
    assert client.get("/api/v1/documents", params={"page_size": 0}).status_code == 422
    assert client.get("/api/v1/documents", params={"page_size": 101}).status_code == 422

    bad_sort = client.get("/api/v1/documents", params={"sort_by": "hack"})
    assert bad_sort.status_code == 400

    bad_order = client.get("/api/v1/documents", params={"sort_order": "sideways"})
    assert bad_order.status_code == 400

    bad_type = client.get("/api/v1/documents", params={"document_type": "unknown"})
    assert bad_type.status_code == 400

    bad_status = client.get("/api/v1/documents", params={"status": "broken"})
    assert bad_status.status_code == 400

    bad_date = client.get("/api/v1/documents", params={"uploaded_from": "not-a-date"})
    assert bad_date.status_code == 422


def test_combined_filters_with_pagination_and_sorting(client):
    keepers = []
    for index in range(4):
        created = _upload(client, f"invoice_{index}.pdf", content=f"%PDF-1.4 keep{index}".encode())
        _set_document_fields(
            client,
            created["id"],
            document_type=DocumentType.INVOICE.value,
            status=DocumentStatus.PROCESSED.value,
            uploaded_at=datetime(2026, 2, index + 1, tzinfo=timezone.utc),
        )
        keepers.append(created)

    noise = _upload(client, "invoice_noise.pdf")
    _set_document_fields(
        client,
        noise["id"],
        document_type=DocumentType.INVOICE.value,
        status=DocumentStatus.FAILED.value,
    )

    response = client.get(
        "/api/v1/documents",
        params={
            "search": "invoice",
            "document_type": "invoice",
            "status": "processed",
            "uploaded_from": "2026-02-01",
            "uploaded_to": "2026-02-28",
            "sort_by": "uploaded_at",
            "sort_order": "asc",
            "page": 1,
            "page_size": 2,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["total_pages"] == 2
    assert payload["has_next"] is True
    assert [item["original_filename"] for item in payload["items"]] == [
        "invoice_0.pdf",
        "invoice_1.pdf",
    ]
