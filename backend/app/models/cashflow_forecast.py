# backend/app/models/cashflow_forecast.py

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
    Integer,
    Boolean,  # ← ADD THIS LINE
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
import enum


class ForecastType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ScenarioType(str, enum.Enum):
    OPTIMISTIC = "optimistic"
    BASELINE = "baseline"
    PESSIMISTIC = "pessimistic"


class CashflowForecast(Base):
    __tablename__ = "cashflow_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Forecast configuration
    forecast_type = Column(Enum(ForecastType), default=ForecastType.MONTHLY)
    scenario = Column(Enum(ScenarioType), default=ScenarioType.BASELINE)

    # Time period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Predicted values (ML-generated)
    predicted_inflow = Column(Numeric(15, 2), default=0.00)
    predicted_outflow = Column(Numeric(15, 2), default=0.00)
    predicted_net = Column(Numeric(15, 2), default=0.00)

    # Breakdown by category
    predicted_sales_receipts = Column(Numeric(15, 2), default=0.00)
    predicted_purchase_payments = Column(Numeric(15, 2), default=0.00)
    predicted_operating_expenses = Column(Numeric(15, 2), default=0.00)
    predicted_salary_payouts = Column(Numeric(15, 2), default=0.00)
    predicted_tax_payments = Column(Numeric(15, 2), default=0.00)
    predicted_loan_emis = Column(Numeric(15, 2), default=0.00)

    # ML metadata
    confidence_score = Column(Numeric(5, 4), default=0.85)  # 0.0000 to 1.0000
    model_version = Column(String(20), default="v1.0")
    features_hash = Column(String(64), nullable=True)  # Hash of input features used

    # Actual values (filled in after period ends — for model retraining)
    actual_inflow = Column(Numeric(15, 2), nullable=True)
    actual_outflow = Column(Numeric(15, 2), nullable=True)
    actual_net = Column(Numeric(15, 2), nullable=True)
    variance = Column(Numeric(15, 2), nullable=True)  # actual_net - predicted_net
    variance_percent = Column(Numeric(6, 2), nullable=True)

    # Advisory flags
    alert_generated = Column(Boolean, default=False)
    alert_severity = Column(String(20), nullable=True)  # low, medium, high

    # Notes
    advisory_notes = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)

    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="cashflow_forecasts")

    def __repr__(self):
        return f"<CashflowForecast {self.forecast_type.value} {self.period_start.date()}>"