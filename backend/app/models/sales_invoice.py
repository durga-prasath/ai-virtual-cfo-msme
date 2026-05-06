# backend/app/models/sales_invoice.py

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Text,
    Numeric,
    DateTime,
    ForeignKey,
    Enum,
    Boolean,        # ← FIXED: Was missing. Needed for synced_to_erp
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
import enum


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    CREDIT = "credit"


class SalesInvoice(Base):
    __tablename__ = "sales_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)

    # Invoice numbering (business-specific series)
    invoice_number = Column(String(50), nullable=False, unique=True)
    invoice_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)

    # Status tracking
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT)

    # Financial summary (denormalized for fast queries)
    subtotal = Column(Numeric(15, 2), default=0.00)
    tax_amount = Column(Numeric(15, 2), default=0.00)
    discount_amount = Column(Numeric(15, 2), default=0.00)
    total_amount = Column(Numeric(15, 2), default=0.00)
    amount_paid = Column(Numeric(15, 2), default=0.00)
    amount_due = Column(Numeric(15, 2), default=0.00)

    # Payment tracking
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    paid_date = Column(DateTime, nullable=True)

    # GST specific
    cgst_total = Column(Numeric(15, 2), default=0.00)
    sgst_total = Column(Numeric(15, 2), default=0.00)
    igst_total = Column(Numeric(15, 2), default=0.00)

    # Notes
    terms = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # ERP sync tracking
    synced_to_erp = Column(Boolean, default=False)
    erp_sync_date = Column(DateTime, nullable=True)
    erp_reference = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="invoices")
    customer = relationship("Customer", back_populates="invoices")
    payments = relationship("Payment", back_populates="sales_invoice")
    revenue_ledgers = relationship("RevenueLedger", back_populates="invoice")
    items = relationship(
        "SalesInvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<SalesInvoice {self.invoice_number}>"