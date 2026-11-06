# backend/app/schemas/invoice_schema.py

from pydantic import BaseModel, Field, field_validator, field_serializer, ConfigDict
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum
import re


# ─────────────────────────────────────────────
# VENDOR SCHEMAS
# ─────────────────────────────────────────────

class VendorCreateSchema(BaseModel):
    user_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=200)
    contact_person: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    gstin: Optional[str] = Field(None, max_length=15)
    pan: Optional[str] = Field(None, max_length=10)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_account_number: Optional[str] = Field(None, max_length=30)
    bank_ifsc: Optional[str] = Field(None, max_length=11)
    upi_id: Optional[str] = Field(None, max_length=50)

    @field_validator('contact_person', 'email', 'phone', 'gstin', 'pan', 'address', 'city', 'state', 'pincode', 'bank_name', 'bank_account_number', 'bank_ifsc', 'upi_id', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator('gstin')
    @classmethod
    def validate_gstin(cls, v):
        if v is not None:
            v = v.upper().strip()
            pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
            if not re.match(pattern, v):
                raise ValueError("Invalid GSTIN format. Example: 33AAPFU0939F1ZV")
        return v



class VendorResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_id: Optional[str] = None
    credit_limit: Decimal = Decimal('0.00')
    outstanding_balance: Decimal = Decimal('0.00')
    is_active: bool
    created_at: datetime


# ─────────────────────────────────────────────
# PURCHASE INVOICE SCHEMAS
# ─────────────────────────────────────────────

class PurchaseInvoiceCreateSchema(BaseModel):
    user_id: Optional[UUID] = None
    vendor_id: UUID
    vendor_invoice_number: Optional[str] = Field(None, max_length=50)
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    received_date: Optional[datetime] = None

    # Financial
    subtotal: Decimal = Field(..., ge=0, decimal_places=2)
    cgst_total: Decimal = Field(default=Decimal('0.00'), ge=0, decimal_places=2)
    sgst_total: Decimal = Field(default=Decimal('0.00'), ge=0, decimal_places=2)
    igst_total: Decimal = Field(default=Decimal('0.00'), ge=0, decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal('0.00'), ge=0, decimal_places=2)

    notes: Optional[str] = None
    terms: Optional[str] = None

    # OCR flags (set automatically during OCR scan, can be overridden)
    ocr_extracted: bool = False
    ocr_confidence: Optional[Decimal] = Field(None, ge=0, le=100)

    @field_validator('subtotal', 'cgst_total', 'sgst_total', 'igst_total',
                     'discount_amount', mode='before')
    @classmethod
    def to_decimal(cls, v):
        if v is None:
            return Decimal('0.00')
        return Decimal(str(v))


class PurchaseInvoiceUpdateSchema(BaseModel):
    """Used to update status or approve a purchase invoice."""
    status: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[datetime] = None


class PurchaseInvoiceResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    vendor_id: UUID
    invoice_number: str
    vendor_invoice_number: Optional[str] = None
    invoice_date: datetime
    due_date: Optional[datetime] = None
    received_date: Optional[datetime] = None
    status: str

    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    amount_due: Decimal

    cgst_total: Decimal
    sgst_total: Decimal
    igst_total: Decimal

    notes: Optional[str] = None
    terms: Optional[str] = None

    ocr_extracted: bool
    ocr_confidence: Optional[Decimal] = None
    uploaded_file_path: Optional[str] = None

    synced_to_erp: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# ─────────────────────────────────────────────
# OCR RESULT SCHEMAS
# ─────────────────────────────────────────────

class OCRFieldResult(BaseModel):
    """Represents a single field extracted from an OCR scan, with its confidence score."""
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    source: str = "ocr"   # "ocr" | "regex" | "manual"


class OCRExtractionResult(BaseModel):
    """
    Full output of an OCR scan on a vendor bill.
    All fields are optional — OCR may not detect all fields.
    Each field carries its own confidence score.
    """
    # Vendor information
    vendor_name: OCRFieldResult = OCRFieldResult()
    vendor_gstin: OCRFieldResult = OCRFieldResult()
    vendor_pan: OCRFieldResult = OCRFieldResult()
    vendor_address: OCRFieldResult = OCRFieldResult()
    vendor_phone: OCRFieldResult = OCRFieldResult()

    # Invoice metadata
    invoice_number: OCRFieldResult = OCRFieldResult()
    invoice_date: OCRFieldResult = OCRFieldResult()
    due_date: OCRFieldResult = OCRFieldResult()

    # Financial fields
    subtotal: OCRFieldResult = OCRFieldResult()
    cgst_amount: OCRFieldResult = OCRFieldResult()
    sgst_amount: OCRFieldResult = OCRFieldResult()
    igst_amount: OCRFieldResult = OCRFieldResult()
    tax_amount: OCRFieldResult = OCRFieldResult()
    total_amount: OCRFieldResult = OCRFieldResult()
    discount_amount: OCRFieldResult = OCRFieldResult()

    # Summary metrics
    overall_confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    raw_text_preview: Optional[str] = None
    page_count: int = 1
    extraction_engine: str = "pdfplumber+regex"
    extraction_warnings: List[str] = []
