# backend/app/schemas/ocr_schema.py

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class DocumentTypeEnum(str, Enum):
    SALARY_SLIP = "SALARY_SLIP"
    BANK_STATEMENT = "BANK_STATEMENT"
    SALES_INVOICE = "SALES_INVOICE"
    VENDOR_INVOICE = "VENDOR_INVOICE"
    EXPENSE_RECEIPT = "EXPENSE_RECEIPT"
    UNKNOWN = "UNKNOWN"


class DocumentFieldResult(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0  # 0 to 100
    source: str = "regex"    # "regex", "heuristic", "ai", "computed"


class ScanDocumentResponse(BaseModel):
    document_type: DocumentTypeEnum
    type_confidence: float = 0.0
    overall_confidence: float = 0.0
    fields: Dict[str, DocumentFieldResult] = Field(default_factory=dict)
    raw_text_preview: str = ""
    suggested_action: str = ""
    warnings: List[str] = Field(default_factory=list)
    page_count: int = 1
    engine: str = "opencv+tesseract"


class ConfirmScanRequest(BaseModel):
    document_type: DocumentTypeEnum
    confirmed_fields: Dict[str, Any]
    notes: Optional[str] = None
    vendor_id: Optional[str] = None
    customer_id: Optional[str] = None


class ConfirmScanResponse(BaseModel):
    created_entity_type: str
    entity_id: Optional[str] = None
    message: str
    status: str = "success"
