# backend/app/models/gst_record.py

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
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
import enum


class ReturnType(str, enum.Enum):
    GSTR1 = "gstr1"           # Outward supplies
    GSTR3B = "gstr3b"         # Monthly/quarterly summary
    GSTR4 = "gstr4"           # Composition dealers
    GSTR9 = "gstr9"           # Annual return


class FilingStatus(str, enum.Enum):
    PENDING = "pending"
    READY_TO_FILE = "ready_to_file"
    FILED = "filed"
    AUTO_FILED = "auto_filed"
    OVERDUE = "overdue"


class GSTRecord(Base):
    __tablename__ = "gst_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Return identification
    return_type = Column(Enum(ReturnType), nullable=False)
    return_period = Column(String(7), nullable=False)  # Format: MM-YYYY

    # Filing timeline
    due_date = Column(DateTime, nullable=False)
    filed_date = Column(DateTime, nullable=True)
    acknowledgement_number = Column(String(20), nullable=True)

    # Filing status
    status = Column(Enum(FilingStatus), default=FilingStatus.PENDING)
    auto_file_enabled = Column(Boolean, default=False)

    # Outward supplies (sales side)
    total_taxable_value = Column(Numeric(15, 2), default=0.00)
    total_exempt_value = Column(Numeric(15, 2), default=0.00)
    total_nil_rated_value = Column(Numeric(15, 2), default=0.00)

    # Tax liability
    total_igst = Column(Numeric(15, 2), default=0.00)
    total_cgst = Column(Numeric(15, 2), default=0.00)
    total_sgst = Column(Numeric(15, 2), default=0.00)
    total_cess = Column(Numeric(15, 2), default=0.00)
    total_tax = Column(Numeric(15, 2), default=0.00)

    # Input Tax Credit (purchase side)
    itc_igst = Column(Numeric(15, 2), default=0.00)
    itc_cgst = Column(Numeric(15, 2), default=0.00)
    itc_sgst = Column(Numeric(15, 2), default=0.00)
    itc_cess = Column(Numeric(15, 2), default=0.00)
    total_itc = Column(Numeric(15, 2), default=0.00)

    # Net tax calculation
    tax_payable = Column(Numeric(15, 2), default=0.00)
    tax_paid = Column(Numeric(15, 2), default=0.00)
    interest_late_fee = Column(Numeric(12, 2), default=0.00)

    # Compliance
    reconciliation_status = Column(String(50), default="pending")
    variance_amount = Column(Numeric(15, 2), default=0.00)

    # GST portal payload (for filing integration)
    json_payload = Column(Text, nullable=True)
    signed_payload = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="gst_records")

    def __repr__(self):
        return f"<GSTRecord {self.return_type.value} {self.return_period}>"