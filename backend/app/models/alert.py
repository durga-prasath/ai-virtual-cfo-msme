# backend/app/models/alert.py

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Text,
    Numeric,  # ← ADD THIS LINE
    DateTime,
    ForeignKey,
    Enum,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
import enum


class AlertType(str, enum.Enum):
    PAYMENT_DUE = "payment_due"
    INVOICE_OVERDUE = "invoice_overdue"
    LOW_CASH_BALANCE = "low_cash_balance"
    GST_FILING_DUE = "gst_filing_due"
    GST_FILING_OVERDUE = "gst_filing_overdue"
    ERP_SYNC_FAILED = "erp_sync_failed"
    EXPENSE_SPIKE = "expense_spike"
    REVENUE_DROP = "revenue_drop"
    CREDIT_LIMIT_BREACH = "credit_limit_breach"
    VENDOR_RISK_ALERT = "vendor_risk_alert"
    CUSTOMER_PAYMENT_DELAY = "customer_payment_delay"
    VIRTUAL_CFO_ADVISORY = "virtual_cfo_advisory"


class AlertSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Alert content
    alert_type = Column(Enum(AlertType), nullable=False)
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.MEDIUM)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)

    # Link to related entity (polymorphic reference)
    related_entity_type = Column(
        String(50),
        nullable=True
    )  # invoice, payment, vendor, customer, gst_record, forecast
    related_entity_id = Column(UUID(as_uuid=True), nullable=True)

    # User interaction
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime, nullable=True)

    # Recommended action
    action_label = Column(String(100), nullable=True)  # e.g., "View Invoice"
    action_url = Column(String(500), nullable=True)     # Frontend route
    action_taken = Column(Boolean, default=False)
    action_taken_at = Column(DateTime, nullable=True)

    # Virtual CFO insight (for ML-generated alerts)
    ai_generated = Column(Boolean, default=False)
    ai_confidence = Column(Numeric(5, 4), nullable=True)
    recommendation = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="alerts")

    def __repr__(self):
        return f"<Alert {self.alert_type.value} [{self.severity.value}]>"