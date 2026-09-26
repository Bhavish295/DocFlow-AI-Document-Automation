import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.rate_limit import enforce_upload_rate_limit
from app.models.user import User
from app.schemas.document import (
    ClassificationResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentTextResponse,
    MessageResponse,
)
from app.schemas.field_intelligence import FieldIntelligenceResponse
from app.schemas.goods_receipt import GoodsReceiptResponse
from app.schemas.invoice import InvoiceResponse
from app.schemas.line_item import DocumentLineItemListResponse
from app.schemas.processing_job import ProcessDocumentResponse, ProcessingJobListResponse
from app.schemas.purchase_order import PurchaseOrderResponse
from app.schemas.rag import DocumentIndexResponse, DocumentIndexStatusResponse
from app.services.audit_service import AuditService
from app.services.document import DocumentService
from app.services.field_intelligence import FieldIntelligenceService
from app.services.document_classification import DocumentClassificationService
from app.services.document_processing import DocumentProcessingService
from app.services.document_processing_job import DocumentProcessingJobService
from app.services.document_processing_orchestrator import DocumentProcessingOrchestrator
from app.services.goods_receipt_extraction_service import GoodsReceiptExtractionService
from app.services.invoice_extraction_service import InvoiceExtractionService
from app.services.line_item_service import LineItemService
from app.services.purchase_order_extraction_service import PurchaseOrderExtractionService
from app.services.rag_indexing import RagIndexingService


router = APIRouter(prefix="/documents")


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.DOCUMENTS_WRITE)),
) -> DocumentResponse:
    enforce_upload_rate_limit(request)
    document = DocumentService(db).create_document(file)
    AuditService(db).log(
        action="document_uploaded",
        user_id=user.id,
        resource_type="document",
        resource_id=document.id,
        details={"filename": document.original_filename},
    )
    return document


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    document_type: str | None = Query(None),
    status: str | None = Query(None),
    uploaded_from: date | None = Query(None),
    uploaded_to: date | None = Query(None),
    sort_by: str = Query("uploaded_at"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> DocumentListResponse:
    return DocumentService(db).list_documents(
        page=page,
        page_size=page_size,
        search=search,
        document_type=document_type,
        status=status,
        uploaded_from=uploaded_from,
        uploaded_to=uploaded_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> DocumentResponse:
    return DocumentService(db).get_document(document_id)


@router.delete("/{document_id}", response_model=MessageResponse)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.DOCUMENTS_WRITE)),
) -> MessageResponse:
    DocumentService(db).delete_document(document_id)
    AuditService(db).log(
        action="document_deleted",
        user_id=user.id,
        resource_type="document",
        resource_id=document_id,
    )
    return MessageResponse(detail="Document deleted successfully.")


@router.post("/{document_id}/process", response_model=ProcessDocumentResponse)
def process_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_PROCESS)),
) -> ProcessDocumentResponse:
    return DocumentProcessingOrchestrator(db).enqueue_process(
        document_id,
        background_tasks=background_tasks,
    )


@router.get("/{document_id}/processing-jobs", response_model=ProcessingJobListResponse)
def list_document_processing_jobs(
    document_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PROCESSING_JOBS_READ)),
) -> ProcessingJobListResponse:
    return DocumentProcessingJobService(db).list_for_document(
        document_id,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}/text", response_model=DocumentTextResponse)
def get_document_text(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> DocumentTextResponse:
    return DocumentProcessingService(db).get_document_text(document_id)


@router.post("/{document_id}/classify", response_model=DocumentResponse)
def classify_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_PROCESS)),
) -> DocumentResponse:
    return DocumentClassificationService(db).classify_document(document_id)


@router.get("/{document_id}/classification", response_model=ClassificationResponse)
def get_document_classification(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> ClassificationResponse:
    return DocumentClassificationService(db).get_classification(document_id)


@router.post("/{document_id}/extract", response_model=InvoiceResponse)
def extract_invoice(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_EXTRACT)),
) -> InvoiceResponse:
    return InvoiceExtractionService(db).extract_for_document(document_id)


@router.get("/{document_id}/invoice", response_model=InvoiceResponse)
def get_document_invoice(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> InvoiceResponse:
    return InvoiceExtractionService(db).get_invoice(document_id)


@router.post("/{document_id}/extract-po", response_model=PurchaseOrderResponse)
def extract_purchase_order(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_EXTRACT)),
) -> PurchaseOrderResponse:
    return PurchaseOrderExtractionService(db).extract_for_document(document_id)


@router.get("/{document_id}/purchase-order", response_model=PurchaseOrderResponse)
def get_document_purchase_order(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> PurchaseOrderResponse:
    return PurchaseOrderExtractionService(db).get_purchase_order(document_id)


@router.post("/{document_id}/extract-grn", response_model=GoodsReceiptResponse)
def extract_goods_receipt(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_EXTRACT)),
) -> GoodsReceiptResponse:
    return GoodsReceiptExtractionService(db).extract_for_document(document_id)


@router.get("/{document_id}/goods-receipt", response_model=GoodsReceiptResponse)
def get_document_goods_receipt(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> GoodsReceiptResponse:
    return GoodsReceiptExtractionService(db).get_goods_receipt(document_id)


@router.get("/{document_id}/line-items", response_model=DocumentLineItemListResponse)
def get_document_line_items(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> DocumentLineItemListResponse:
    return LineItemService(db).list_for_document(document_id)


@router.post("/{document_id}/extract-line-items", response_model=DocumentLineItemListResponse)
def extract_document_line_items(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_EXTRACT)),
) -> DocumentLineItemListResponse:
    return LineItemService(db).extract_for_document(document_id)


@router.get("/{document_id}/field-intelligence", response_model=FieldIntelligenceResponse)
def get_field_intelligence(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> FieldIntelligenceResponse:
    return FieldIntelligenceService(db).get_for_document(document_id)


@router.post("/{document_id}/index", response_model=DocumentIndexResponse)
def index_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_INDEX)),
) -> DocumentIndexResponse:
    return RagIndexingService(db).index_document(document_id)


@router.get("/{document_id}/index-status", response_model=DocumentIndexStatusResponse)
def get_document_index_status(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> DocumentIndexStatusResponse:
    return RagIndexingService(db).get_index_status(document_id)
