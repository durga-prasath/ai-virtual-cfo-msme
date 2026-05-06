# backend/app/models/sales_invoice_item.py

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    ForeignKey,
    DateTime,
    Numeric,
    Text,           # Needed for description
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class SalesInvoiceItem(Base):
    __tablename__ = "sales_invoice_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_invoices.id"),
        nullable=False
    )
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False
    )

    # Line item details
    description = Column(Text, nullable=False)
    quantity = Column(Numeric(10, 3), default=1.000)
    unit_price = Column(Numeric(12, 2), nullable=False)

    # GST per line item
    gst_rate = Column(Numeric(5, 2), default=18.00)
    cgst_amount = Column(Numeric(12, 2), default=0.00)
    sgst_amount = Column(Numeric(12, 2), default=0.00)
    igst_amount = Column(Numeric(12, 2), default=0.00)

    # Calculated total
    total = Column(Numeric(15, 2), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    invoice = relationship("SalesInvoice", back_populates="items")
    product = relationship("Product", back_populates="invoice_items")

    def __repr__(self):
        return f"<SalesInvoiceItem {self.description[:20]}>"