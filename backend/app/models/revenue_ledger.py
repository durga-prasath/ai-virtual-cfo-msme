# backend/app/models/revenue_ledger.py

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


class LedgerEntryType(str, enum.Enum):
    INVOICE_RAISED = "invoice_raised"
    PAYMENT_RECEIVED = "payment_received"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    REVENUE_ADJUSTMENT = "revenue_adjustment"
    BAD_DEBT_WRITE_OFF = "bad_debt_write_off"


class RevenueLedger(Base):
    __tablename__ = "revenue_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Source documents
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_invoices.id"),
        nullable=True
    )
    payment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payments.id"),
        nullable=True
    )
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=True
    )

    # Entry details
    entry_date = Column(DateTime, nullable=False)
    entry_type = Column(Enum(LedgerEntryType), nullable=False)
    reference_number = Column(String(50), nullable=True)

    # Financials
    gross_amount = Column(Numeric(15, 2), default=0.00)
    discount_amount = Column(Numeric(15, 2), default=0.00)
    taxable_amount = Column(Numeric(15, 2), default=0.00)
    cgst_amount = Column(Numeric(15, 2), default=0.00)
    sgst_amount = Column(Numeric(15, 2), default=0.00)
    igst_amount = Column(Numeric(15, 2), default=0.00)
    cess_amount = Column(Numeric(15, 2), default=0.00)
    total_tax = Column(Numeric(15, 2), default=0.00)
    net_amount = Column(Numeric(15, 2), default=0.00)

    # Description
    description = Column(Text, nullable=True)

    # Accounting period
    financial_year = Column(String(9), nullable=False)  # e.g., 2024-2025
    quarter = Column(String(2), nullable=False)         # Q1, Q2, Q3, Q4
    month = Column(String(3), nullable=True)            # APR, MAY, etc.

    # ERP sync
    synced_to_erp = Column(Boolean, default=False)
    erp_sync_date = Column(DateTime, nullable=True)
    erp_reference = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="revenue_ledgers")
    invoice = relationship("SalesInvoice", back_populates="revenue_ledgers")
    payment = relationship("Payment", back_populates="revenue_ledgers")
    customer = relationship("Customer", back_populates="revenue_ledgers")

    def __repr__(self):
        return f"<RevenueLedger {self.entry_type.value} {self.net_amount}>"