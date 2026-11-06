# backend/app/schemas/payment_schema.py

from pydantic import BaseModel, Field, field_validator, ConfigDict
from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import datetime
from enum import Enum


class PaymentMethodEnum(str, Enum):
    CASH = "cash"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    NEFT = "neft"
    RTGS = "rtgs"
    IMPS = "imps"


class PaymentStatusEnum(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentDirectionEnum(str, Enum):
    INCOMING = "incoming"   # Customer paid you
    OUTGOING = "outgoing"   # You paid vendor


# ─────────────────────────────────────────────
# PAYMENT CREATE
# ─────────────────────────────────────────────

class PaymentCreateSchema(BaseModel):
    """
    What the client sends to record a payment.

    For a customer paying a sales invoice:
        sales_invoice_id = <invoice uuid>
        customer_id      = <customer uuid>
        direction        = "incoming"

    For you paying a vendor:
        purchase_invoice_id = <invoice uuid>
        vendor_id           = <vendor uuid>
        direction           = "outgoing"
    """
    sales_invoice_id: Optional[UUID] = None
    purchase_invoice_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    vendor_id: Optional[UUID] = None

    amount: Decimal = Field(..., gt=0, decimal_places=2)
    payment_method: PaymentMethodEnum
    direction: PaymentDirectionEnum
    payment_date: Optional[datetime] = None

    # India-specific payment tracking
    transaction_reference: Optional[str] = Field(None, max_length=100)
    utr_number: Optional[str] = Field(
        None,
        max_length=50,
        description="UTR number for NEFT/RTGS/IMPS transactions"
    )
    upi_transaction_id: Optional[str] = Field(None, max_length=50)
    bank_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None

    @field_validator('amount', mode='before')
    @classmethod
    def to_decimal(cls, v):
        return Decimal(str(v))


class PaymentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    sales_invoice_id: Optional[UUID]
    purchase_invoice_id: Optional[UUID]
    customer_id: Optional[UUID]
    vendor_id: Optional[UUID]
    amount: Decimal
    payment_method: str
    direction: str
    status: str
    payment_date: datetime
    transaction_reference: Optional[str]
    utr_number: Optional[str]
    upi_transaction_id: Optional[str]
    bank_reference: Optional[str]
    is_reconciled: bool
    notes: Optional[str]
    created_at: datetime


# ─────────────────────────────────────────────
# INVOICE STATUS UPDATE
# ─────────────────────────────────────────────

class InvoiceStatusUpdateSchema(BaseModel):
    """Used for manually updating invoice status."""
    status: str = Field(..., description="sent | cancelled")