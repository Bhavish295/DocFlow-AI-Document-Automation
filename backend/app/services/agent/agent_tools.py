"""Registered read-only / safely analytical agent tools wrapping existing services."""

from __future__ import annotations

from typing import Any
import uuid

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import Permission
from app.models.document_review import DocumentReview
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.models.validation import DocumentValidation
from app.services.agent.agent_registry import AgentToolDefinition, AgentToolRegistry
from app.services.anomaly_service import AnomalyService
from app.services.document import DocumentService
from app.services.document_classification import DocumentClassificationService
from app.services.document_processing import DocumentProcessingService
from app.services.document_review import DocumentReviewService
from app.services.duplicate_detection import DuplicateDetectionService
from app.services.field_intelligence import FieldIntelligenceService
from app.services.goods_receipt_extraction_service import GoodsReceiptExtractionService
from app.services.investigation_agent import InvestigationAgent
from app.services.invoice_extraction_service import InvoiceExtractionService
from app.services.line_item_service import LineItemService
from app.services.purchase_order_extraction_service import PurchaseOrderExtractionService
from app.services.rag_answer import RagAnswerService
from app.services.sql_agent import SqlAgentService
from app.services.three_way_matching import ThreeWayMatchingService
from app.services.validation_service import ValidationService


class DocumentIdInput(BaseModel):
    document_id: uuid.UUID


class SearchDocumentsInput(BaseModel):
    search: str | None = Field(default=None, max_length=200)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=50)
    document_type: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=50)


class InvoiceNumberInput(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=100)


class ReviewIdInput(BaseModel):
    review_id: uuid.UUID


class ListReviewsInput(BaseModel):
    status: str | None = Field(default=None, max_length=50)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=50)


class ListValidationsInput(BaseModel):
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=50)


class ValidateInvoicePoInput(BaseModel):
    invoice_id: uuid.UUID
    purchase_order_id: uuid.UUID


class ThreeWayMatchIdInput(BaseModel):
    match_id: uuid.UUID


class QuestionInput(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    max_rows: int | None = Field(default=None, ge=1, le=100)


class RagQueryInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_id: uuid.UUID | None = None
    document_type: str | None = Field(default=None, max_length=50)


class RagAskInput(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_id: uuid.UUID | None = None
    document_type: str | None = Field(default=None, max_length=50)


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return value


def _summarize(payload: Any, *, limit: int = 400) -> str:
    if payload is None:
        return "No data."
    if isinstance(payload, str):
        return payload[:limit]
    if isinstance(payload, dict):
        keys = ", ".join(list(payload.keys())[:12])
        return f"Object with keys: {keys}"[:limit]
    if isinstance(payload, list):
        return f"{len(payload)} item(s)"[:limit]
    text = str(payload)
    return text[:limit]


def _parse(model: type[BaseModel], arguments: dict[str, Any]) -> BaseModel:
    try:
        return model.model_validate(arguments or {})
    except ValidationError as exc:
        raise AppError(f"Invalid tool input: {exc.errors()[0].get('msg', 'validation failed')}", status_code=400) from exc


def find_invoice_by_number(db: Session, invoice_number: str) -> Invoice | None:
    needle = (invoice_number or "").strip()
    if not needle:
        return None
    exact = db.scalar(select(Invoice).where(func.lower(Invoice.invoice_number) == needle.lower()).limit(1))
    if exact is not None:
        return exact
    return db.scalar(
        select(Invoice).where(Invoice.invoice_number.ilike(f"%{needle}%")).limit(1)
    )


def find_document_id_for_invoice_number(db: Session, invoice_number: str) -> uuid.UUID | None:
    invoice = find_invoice_by_number(db, invoice_number)
    return invoice.document_id if invoice else None


def build_default_registry(db: Session) -> AgentToolRegistry:
    registry = AgentToolRegistry()

    def get_document(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        doc = DocumentService(db).get_document(args.document_id)
        data = _model_dump(doc)
        return {"document": data, "summary": f"Document {doc.original_filename} status={doc.status}"}

    def search_documents(**kwargs: Any) -> dict[str, Any]:
        args = _parse(SearchDocumentsInput, kwargs)
        result = DocumentService(db).list_documents(
            page=args.page,
            page_size=args.page_size,
            search=args.search,
            document_type=args.document_type,
            status=args.status,
        )
        data = _model_dump(result)
        return {
            "total": result.total,
            "items": [
                {
                    "id": str(item.id),
                    "filename": item.original_filename,
                    "status": item.status,
                    "document_type": item.document_type,
                }
                for item in result.items
            ],
            "summary": f"Found {result.total} document(s)",
            "raw": data,
        }

    def get_document_text(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        text = DocumentProcessingService(db).get_document_text(args.document_id)
        content = (text.extracted_text or "")[:2000]
        return {
            "document_id": str(args.document_id),
            "char_count": len(text.extracted_text or ""),
            "excerpt": content,
            "summary": f"Extracted text length={len(text.extracted_text or '')}",
        }

    def get_document_classification(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        result = DocumentClassificationService(db).get_classification(args.document_id)
        data = _model_dump(result)
        return {
            "classification": data,
            "summary": f"Type={getattr(result, 'document_type', None)} confidence={getattr(result, 'classification_confidence', None)}",
        }

    def get_field_intelligence(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        result = FieldIntelligenceService(db).get_for_document(args.document_id)
        data = _model_dump(result)
        issues = getattr(result, "issues", None) or []
        return {
            "field_intelligence": data,
            "summary": (
                f"Field intelligence status={getattr(result, 'overall_status', None)}; "
                f"issues={len(issues)}; review_required={getattr(result, 'review_required', None)}"
            ),
        }

    def get_line_items(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        result = LineItemService(db).list_for_document(args.document_id)
        items = list(result.items or [])
        return {
            "count": len(items),
            "items": [
                {
                    "description": getattr(item, "description", None),
                    "sku": getattr(item, "sku", None),
                    "quantity": str(getattr(item, "quantity", None)),
                    "unit_price": str(getattr(item, "unit_price", None)),
                }
                for item in items[:30]
            ],
            "summary": f"{len(items)} line item(s)",
        }

    def get_invoice(**kwargs: Any) -> dict[str, Any]:
        if kwargs.get("invoice_number") and not kwargs.get("document_id"):
            inv_args = _parse(InvoiceNumberInput, kwargs)
            invoice = find_invoice_by_number(db, inv_args.invoice_number)
            if invoice is None:
                raise AppError("Invoice not found for that number.", status_code=404)
            document_id = invoice.document_id
        else:
            args = _parse(DocumentIdInput, kwargs)
            document_id = args.document_id
        result = InvoiceExtractionService(db).get_invoice(document_id)
        data = _model_dump(result)
        return {
            "invoice": data,
            "document_id": str(document_id),
            "summary": f"Invoice {getattr(result, 'invoice_number', None)} total={getattr(result, 'total_amount', None)}",
        }

    def get_purchase_order(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        result = PurchaseOrderExtractionService(db).get_purchase_order(args.document_id)
        data = _model_dump(result)
        return {
            "purchase_order": data,
            "summary": f"PO {getattr(result, 'po_number', None)} total={getattr(result, 'total_amount', None)}",
        }

    def get_goods_receipt(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        result = GoodsReceiptExtractionService(db).get_goods_receipt(args.document_id)
        data = _model_dump(result)
        return {
            "goods_receipt": data,
            "summary": f"GRN {getattr(result, 'grn_number', None)}",
        }

    def validate_invoice_po(**kwargs: Any) -> dict[str, Any]:
        """Analytical compare using existing validation service (creates a validation record)."""
        args = _parse(ValidateInvoicePoInput, kwargs)
        existing = db.scalar(
            select(DocumentValidation)
            .where(
                DocumentValidation.invoice_id == args.invoice_id,
                DocumentValidation.purchase_order_id == args.purchase_order_id,
            )
            .order_by(DocumentValidation.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            response = ValidationService(db).get_validation(existing.id)
            data = _model_dump(response)
            return {
                "validation": data,
                "reused_existing": True,
                "summary": f"Existing validation status={existing.status}",
            }
        result = ValidationService(db).validate_invoice_against_po(
            args.invoice_id,
            args.purchase_order_id,
            create_review=False,
        )
        data = _model_dump(result)
        return {
            "validation": data,
            "reused_existing": False,
            "summary": f"Validation status={result.status}",
        }

    def get_three_way_match(**kwargs: Any) -> dict[str, Any]:
        if kwargs.get("match_id"):
            args = _parse(ThreeWayMatchIdInput, kwargs)
            result = ThreeWayMatchingService(db).get_match(args.match_id)
            data = _model_dump(result)
            return {"match": data, "summary": f"Three-way match status={result.status}"}
        # Latest matches list as fallback
        listed = ThreeWayMatchingService(db).list_matches(page=1, page_size=5)
        return {
            "matches": [
                {"id": str(item.id), "status": item.status}
                for item in listed.items
            ],
            "summary": f"{listed.total} three-way match record(s)",
        }

    def list_validation_results(**kwargs: Any) -> dict[str, Any]:
        args = _parse(ListValidationsInput, kwargs)
        result = ValidationService(db).list_validations(page=args.page, page_size=args.page_size)
        return {
            "total": result.total,
            "items": [
                {
                    "id": str(item.id),
                    "status": item.status,
                    "invoice_number": item.invoice_number,
                    "po_number": item.po_number,
                    "mismatch_summary": item.mismatch_summary,
                }
                for item in result.items
            ],
            "summary": f"{result.total} validation result(s)",
        }

    def get_review(**kwargs: Any) -> dict[str, Any]:
        if kwargs.get("review_id"):
            args = _parse(ReviewIdInput, kwargs)
            result = DocumentReviewService(db).get_review(args.review_id)
            data = _model_dump(result)
            return {"review": data, "summary": f"Review status={result.status} reason={result.reason}"}
        if kwargs.get("document_id"):
            args = _parse(DocumentIdInput, kwargs)
            review = db.scalar(
                select(DocumentReview)
                .where(DocumentReview.document_id == args.document_id)
                .order_by(DocumentReview.created_at.desc())
                .limit(1)
            )
            if review is None:
                return {"review": None, "summary": "No review found for document"}
            result = DocumentReviewService(db).get_review(review.id)
            data = _model_dump(result)
            return {"review": data, "summary": f"Review status={result.status} reason={result.reason}"}
        raise AppError("review_id or document_id is required.", status_code=400)

    def list_reviews(**kwargs: Any) -> dict[str, Any]:
        args = _parse(ListReviewsInput, kwargs)
        result = DocumentReviewService(db).list_reviews(
            status=args.status,
            page=args.page,
            page_size=args.page_size,
        )
        return {
            "total": result.total,
            "items": [
                {
                    "id": str(item.id),
                    "document_id": str(item.document_id),
                    "status": item.status,
                    "reason": item.reason,
                    "priority": item.priority,
                }
                for item in result.items
            ],
            "summary": f"{result.total} review(s)",
        }

    def check_document_duplicates(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        # Read-only path: return existing findings without re-running detection writes.
        result = DuplicateDetectionService(db).list_for_document(args.document_id)
        return {
            "duplicates": result,
            "summary": f"Duplicate findings for document={args.document_id}",
        }

    def get_duplicate_findings(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        result = DuplicateDetectionService(db).summary_for_document(args.document_id)
        return {"findings": result, "summary": "Duplicate summary retrieved"}

    def get_anomaly_summary(**kwargs: Any) -> dict[str, Any]:
        result = AnomalyService(db).summary()
        return {"summary_data": result, "summary": "Anomaly summary retrieved"}

    def get_document_anomaly(**kwargs: Any) -> dict[str, Any]:
        args = _parse(DocumentIdInput, kwargs)
        result = AnomalyService(db).get_anomaly_for_document(args.document_id)
        return {"anomaly": result, "summary": f"Anomaly for document={args.document_id}"}

    def search_knowledge(**kwargs: Any) -> dict[str, Any]:
        args = _parse(RagQueryInput, kwargs)
        result = RagAnswerService(db).search(
            args.query,
            top_k=args.top_k,
            document_id=args.document_id,
            document_type=args.document_type,
        )
        data = _model_dump(result)
        return {"search": data, "summary": f"RAG search returned {len(getattr(result, 'results', []) or getattr(result, 'chunks', []) or [])} hit(s)"}

    def ask_knowledge(**kwargs: Any) -> dict[str, Any]:
        args = _parse(RagAskInput, kwargs)
        result = RagAnswerService(db).ask(
            args.question,
            top_k=args.top_k,
            document_id=args.document_id,
            document_type=args.document_type,
        )
        data = _model_dump(result)
        return {
            "answer": getattr(result, "answer", None),
            "rag": data,
            "summary": (getattr(result, "answer", None) or "RAG answer produced")[:300],
        }

    def execute_safe_sql_question(**kwargs: Any) -> dict[str, Any]:
        args = _parse(QuestionInput, kwargs)
        result = SqlAgentService(db).ask(args.question, max_rows=args.max_rows)
        return {
            "sql_result": result,
            "summary": (result.get("answer") or f"SQL status={result.get('status')}")[:400],
        }

    def run_investigation(**kwargs: Any) -> dict[str, Any]:
        args = _parse(QuestionInput, kwargs)
        result = InvestigationAgent(db).investigate(args.question)
        return {
            "investigation": result,
            "summary": (result.get("summary") or f"Investigation status={result.get('status')}")[:400],
        }

    def resolve_related_po_grn(**kwargs: Any) -> dict[str, Any]:
        """Locate related PO/GRN document ids for an invoice document via shared vendor/PO fields."""
        args = _parse(DocumentIdInput, kwargs)
        invoice = db.scalar(select(Invoice).where(Invoice.document_id == args.document_id))
        if invoice is None:
            return {"related": {}, "summary": "No invoice on document"}
        related: dict[str, Any] = {"invoice_id": str(invoice.id), "invoice_document_id": str(args.document_id)}
        po = None
        po_number = getattr(invoice, "po_number", None)
        if po_number:
            po = db.scalar(
                select(PurchaseOrder).where(PurchaseOrder.po_number.ilike(str(po_number))).limit(1)
            )
        if po is None and invoice.vendor_name:
            po = db.scalar(
                select(PurchaseOrder)
                .where(PurchaseOrder.vendor_name.ilike(invoice.vendor_name))
                .limit(1)
            )
        if po is not None:
            related["purchase_order_id"] = str(po.id)
            related["purchase_order_document_id"] = str(po.document_id)
            related["po_number"] = po.po_number
        return {"related": related, "summary": f"Related entities resolved keys={list(related.keys())}"}

    tools = [
        AgentToolDefinition(
            name="get_document",
            description="Get document metadata by UUID",
            category="documents",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_document,
        ),
        AgentToolDefinition(
            name="search_documents",
            description="Search documents with safe pagination",
            category="documents",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"search": "string", "page": "int", "page_size": "int"},
            handler=search_documents,
        ),
        AgentToolDefinition(
            name="get_document_text",
            description="Get extracted document text excerpt",
            category="documents",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_document_text,
        ),
        AgentToolDefinition(
            name="get_document_classification",
            description="Get document classification details",
            category="documents",
            required_permission=Permission.CLASSIFICATION_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_document_classification,
        ),
        AgentToolDefinition(
            name="get_field_intelligence",
            description="Get field intelligence findings for a document",
            category="documents",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_field_intelligence,
        ),
        AgentToolDefinition(
            name="get_line_items",
            description="List line items for a document",
            category="documents",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_line_items,
        ),
        AgentToolDefinition(
            name="get_invoice",
            description="Get invoice data by document id or invoice number",
            category="invoice",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid", "invoice_number": "string"},
            handler=get_invoice,
        ),
        AgentToolDefinition(
            name="get_purchase_order",
            description="Get purchase order data by document id",
            category="invoice",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_purchase_order,
        ),
        AgentToolDefinition(
            name="get_goods_receipt",
            description="Get goods receipt data by document id",
            category="invoice",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_goods_receipt,
        ),
        AgentToolDefinition(
            name="resolve_related_po_grn",
            description="Resolve related PO identifiers for an invoice document",
            category="invoice",
            required_permission=Permission.DOCUMENTS_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=resolve_related_po_grn,
        ),
        AgentToolDefinition(
            name="validate_invoice_po",
            description="Compare invoice vs PO using existing validation (reuses existing result when present)",
            category="validation",
            required_permission=Permission.VALIDATIONS_WRITE,
            read_only=True,  # treated as analytical; prefers existing row
            input_schema={"invoice_id": "uuid", "purchase_order_id": "uuid"},
            handler=validate_invoice_po,
        ),
        AgentToolDefinition(
            name="get_three_way_match",
            description="Get three-way match by id or list recent matches",
            category="validation",
            required_permission=Permission.VALIDATIONS_READ,
            read_only=True,
            input_schema={"match_id": "uuid"},
            handler=get_three_way_match,
        ),
        AgentToolDefinition(
            name="list_validation_results",
            description="List stored invoice↔PO validation results",
            category="validation",
            required_permission=Permission.VALIDATIONS_READ,
            read_only=True,
            input_schema={"page": "int", "page_size": "int"},
            handler=list_validation_results,
        ),
        AgentToolDefinition(
            name="get_review",
            description="Get a review by review_id or document_id",
            category="review",
            required_permission=Permission.REVIEWS_READ,
            read_only=True,
            input_schema={"review_id": "uuid", "document_id": "uuid"},
            handler=get_review,
        ),
        AgentToolDefinition(
            name="list_reviews",
            description="List review queue items",
            category="review",
            required_permission=Permission.REVIEWS_READ,
            read_only=True,
            input_schema={"status": "string", "page": "int"},
            handler=list_reviews,
        ),
        AgentToolDefinition(
            name="check_document_duplicates",
            description="Read existing duplicate findings for a document (no resolve/write)",
            category="duplicates",
            required_permission=Permission.DUPLICATES_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=check_document_duplicates,
        ),
        AgentToolDefinition(
            name="get_duplicate_findings",
            description="Get duplicate summary for a document",
            category="duplicates",
            required_permission=Permission.DUPLICATES_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_duplicate_findings,
        ),
        AgentToolDefinition(
            name="get_anomaly_summary",
            description="Get anomaly detection summary",
            category="anomaly",
            required_permission=Permission.ANOMALIES_READ,
            read_only=True,
            input_schema={},
            handler=get_anomaly_summary,
        ),
        AgentToolDefinition(
            name="get_document_anomaly",
            description="Get anomaly score for a document",
            category="anomaly",
            required_permission=Permission.ANOMALIES_READ,
            read_only=True,
            input_schema={"document_id": "uuid"},
            handler=get_document_anomaly,
        ),
        AgentToolDefinition(
            name="search_knowledge",
            description="Semantic search over indexed document knowledge",
            category="rag",
            required_permission=Permission.RAG_USE,
            read_only=True,
            input_schema={"query": "string"},
            handler=search_knowledge,
        ),
        AgentToolDefinition(
            name="ask_knowledge",
            description="Ask a grounded question over indexed documents",
            category="rag",
            required_permission=Permission.RAG_USE,
            read_only=True,
            input_schema={"question": "string"},
            handler=ask_knowledge,
        ),
        AgentToolDefinition(
            name="execute_safe_sql_question",
            description="Ask a read-only business-data question via the SQL safety layer",
            category="sql",
            required_permission=Permission.SQL_USE,
            read_only=True,
            input_schema={"question": "string", "max_rows": "int"},
            handler=execute_safe_sql_question,
        ),
        AgentToolDefinition(
            name="run_investigation",
            description="Run the existing read-only investigation agent",
            category="investigation",
            required_permission=Permission.INVESTIGATION_USE,
            read_only=True,
            input_schema={"question": "string"},
            handler=run_investigation,
        ),
    ]

    for tool in tools:
        registry.register(tool)
    return registry


__all__ = [
    "build_default_registry",
    "find_document_id_for_invoice_number",
    "find_invoice_by_number",
    "_summarize",
]
