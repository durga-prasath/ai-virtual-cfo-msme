# backend/app/schemas/billing_schema.py

from pydantic import BaseModel, Field, field_validator, ConfigDict
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from datetime import datetime, date
from enum import Enum
import re


class GSTTypeEnum(str, Enum):
    INTRA = "INTRA"   # Same state → CGST + SGST
    INTER = "INTER"   # Different state → IGST


# ─────────────────────────────────────────────
# CUSTOMER SCHEMAS
# ─────────────────────────────────────────────

class CustomerCreateSchema(BaseModel):
    user_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)

    @field_validator('gstin')
    @classmethod
    def validate_gstin(cls, v):
        if v is not None:
            v = v.upper().strip()
            pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
            if not re.match(pattern, v):
                raise ValueError("Invalid GSTIN format. Example: 33AAPFU0939F1ZV")
        return v


class CustomerResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    email: Optional[str]
    phone: Optional[str]
    gstin: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    is_active: bool
    created_at: datetime


# ─────────────────────────────────────────────
# PRODUCT SCHEMAS
# ─────────────────────────────────────────────

class ProductCreateSchema(BaseModel):
    user_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    hsn_code: Optional[str] = Field(None, max_length=8)
    base_price: Decimal = Field(..., gt=0, decimal_places=2)
    gst_rate: Decimal = Field(..., ge=0, le=28, decimal_places=2)
    unit: Optional[str] = Field(default="PCS", max_length=20)

    @field_validator('base_price', 'gst_rate', mode='before')
    @classmethod
    def to_decimal(cls, v):
        return Decimal(str(v))

    @field_validator('gst_rate')
    @classmethod
    def validate_gst_slab(cls, v):
        valid = {Decimal('0'), Decimal('5'), Decimal('12'), Decimal('18'), Decimal('28')}
        if Decimal(str(v)) not in valid:
            raise ValueError("GST rate must be one of: 0, 5, 12, 18, 28")
        return v


class ProductResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: Optional[str]
    hsn_code: Optional[str]
    base_price: Decimal
    gst_rate: Decimal
    unit: Optional[str]
    is_active: bool
    created_at: datetime


# ─────────────────────────────────────────────
# INVOICE SCHEMAS
# ─────────────────────────────────────────────

class InvoiceItemCreateSchema(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., gt=0)

    @field_validator('quantity', 'unit_price', mode='before')
    @classmethod
    def to_decimal(cls, v):
        return Decimal(str(v))


class InvoiceItemResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    gst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total: Decimal


class InvoiceCreateSchema(BaseModel):
    user_id: Optional[UUID] = None
    customer_id: UUID
    gst_type: GSTTypeEnum
    due_date: Optional[date] = None
    notes: Optional[str] = None
    items: List[InvoiceItemCreateSchema] = Field(..., min_length=1)


class InvoiceResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    customer_id: UUID
    invoice_number: str
    invoice_date: datetime
    due_date: Optional[datetime]
    status: str
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    cgst_total: Decimal
    sgst_total: Decimal
    igst_total: Decimal
    notes: Optional[str]
    created_at: datetime
    items: List[InvoiceItemResponseSchema]