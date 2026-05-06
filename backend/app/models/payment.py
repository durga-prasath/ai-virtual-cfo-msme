# backend/app/models/payment.py

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


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentDirection(str, enum.Enum):
    INCOMING = "incoming"   # Customer paid you (for sales invoice)
    OUTGOING = "outgoing"   # You paid vendor (for purchase invoice)


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    NEFT = "neft"
    RTGS = "rtgs"
    IMPS = "imps"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Link to invoice (one of these will be set, the other null)
    sales_invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_invoices.id"),
        nullable=True
    )
    purchase_invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_invoices.id"),
        nullable=True
    )

    # Link to party
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True)

    # Transaction details
    transaction_reference = Column(String(100), nullable=True, unique=True)
    amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    payment_date = Column(DateTime, default=datetime.utcnow)

    # Classification
    status = Column(Enum(PaymentStatus), default=PaymentStatus.COMPLETED)
    direction = Column(Enum(PaymentDirection), nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False)

    # Banking details (India-specific)
    utr_number = Column(String(50), nullable=True)  # UTR for NEFT/RTGS/IMPS
    bank_reference = Column(String(100), nullable=True)
    upi_transaction_id = Column(String(50), nullable=True)

    # Reconciliation
    is_reconciled = Column(Boolean, default=False)
    reconciled_date = Column(DateTime, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="payments")
    sales_invoice = relationship("SalesInvoice", back_populates="payments")
    purchase_invoice = relationship("PurchaseInvoice", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")
    vendor = relationship("Vendor", back_populates="payments")
    revenue_ledgers = relationship("RevenueLedger", back_populates="payment")

    def __repr__(self):
        return f"<Payment {self.direction.value} {self.amount}>"