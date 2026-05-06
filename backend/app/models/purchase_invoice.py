# backend/app/models/purchase_invoice.py

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
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
import enum


class PurchaseInvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    RECEIVED = "received"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)

    # Invoice numbering
    invoice_number = Column(String(50), nullable=False)
    vendor_invoice_number = Column(String(50), nullable=True)

    # Dates
    invoice_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)
    received_date = Column(DateTime, nullable=True)

    # Status
    status = Column(Enum(PurchaseInvoiceStatus), default=PurchaseInvoiceStatus.DRAFT)

    # Financial summary
    subtotal = Column(Numeric(15, 2), default=0.00)
    tax_amount = Column(Numeric(15, 2), default=0.00)
    discount_amount = Column(Numeric(15, 2), default=0.00)
    total_amount = Column(Numeric(15, 2), default=0.00)
    amount_paid = Column(Numeric(15, 2), default=0.00)
    amount_due = Column(Numeric(15, 2), default=0.00)

    # GST specific
    cgst_total = Column(Numeric(15, 2), default=0.00)
    sgst_total = Column(Numeric(15, 2), default=0.00)
    igst_total = Column(Numeric(15, 2), default=0.00)

    # Notes
    terms = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # OCR / document tracking
    ocr_extracted = Column(Boolean, default=False)
    ocr_confidence = Column(Numeric(5, 2), nullable=True)
    uploaded_file_path = Column(String(500), nullable=True)

    # ERP sync tracking
    synced_to_erp = Column(Boolean, default=False)
    erp_sync_date = Column(DateTime, nullable=True)
    erp_reference = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    payments = relationship("Payment", back_populates="purchase_invoice")
    user = relationship("User", back_populates="purchase_invoices")
    vendor = relationship("Vendor", back_populates="purchase_invoices")

    def __repr__(self):
        return f"<PurchaseInvoice {self.invoice_number}>"