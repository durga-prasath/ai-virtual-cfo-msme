# backend/app/schemas/forecast_schema.py

from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from enum import Enum


# ─────────────────────────────────────────────
# ENUMS (mirrored from models for API layer)
# ─────────────────────────────────────────────

class ForecastTypeEnum(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ScenarioTypeEnum(str, Enum):
    OPTIMISTIC = "optimistic"
    BASELINE = "baseline"
    PESSIMISTIC = "pessimistic"


class AlertTypeEnum(str, Enum):
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


class AlertSeverityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─────────────────────────────────────────────
# FORECAST SCHEMAS
# ─────────────────────────────────────────────

class ForecastRequestSchema(BaseModel):
    """Input to generate a new cash flow forecast."""
    forecast_type: ForecastTypeEnum = ForecastTypeEnum.MONTHLY
    scenario: ScenarioTypeEnum = ScenarioTypeEnum.BASELINE
    periods_ahead: int = Field(default=3, ge=1, le=12,
        description="Number of periods to forecast (1–12)")


class ForecastPeriodSchema(BaseModel):
    """A single forecast data point (one period)."""
    period_label: str            # e.g. "Oct 2024", "Q1 2025", "Week 42"
    period_start: datetime
    period_end: datetime
    scenario: ScenarioTypeEnum

    predicted_inflow: Decimal
    predicted_outflow: Decimal
    predicted_net: Decimal

    predicted_sales_receipts: Decimal
    predicted_purchase_payments: Decimal
    predicted_operating_expenses: Decimal
    predicted_salary_payouts: Decimal
    predicted_tax_payments: Decimal
    predicted_loan_emis: Decimal

    confidence_score: float       # 0.0 – 1.0
    model_version: str
    advisory_notes: Optional[str] = None
    recommendation: Optional[str] = None


class ForecastResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    forecast_type: str
    scenario: str
    period_start: datetime
    period_end: datetime

    predicted_inflow: Decimal
    predicted_outflow: Decimal
    predicted_net: Decimal

    predicted_sales_receipts: Decimal
    predicted_purchase_payments: Decimal
    predicted_operating_expenses: Decimal
    predicted_salary_payouts: Decimal
    predicted_tax_payments: Decimal
    predicted_loan_emis: Decimal

    confidence_score: Decimal
    model_version: str
    advisory_notes: Optional[str] = None
    recommendation: Optional[str] = None
    alert_generated: bool
    alert_severity: Optional[str] = None

    actual_inflow: Optional[Decimal] = None
    actual_outflow: Optional[Decimal] = None
    actual_net: Optional[Decimal] = None
    variance: Optional[Decimal] = None
    variance_percent: Optional[Decimal] = None

    generated_at: datetime


class ForecastListResponse(BaseModel):
    """Wraps a multi-period forecast generation result."""
    scenario: ScenarioTypeEnum
    forecast_type: ForecastTypeEnum
    periods: List[ForecastResponseSchema]
    generated_at: datetime
    summary: dict   # quick totals across all periods


# ─────────────────────────────────────────────
# DASHBOARD SCHEMAS
# ─────────────────────────────────────────────

class ReceivablesAgingBucket(BaseModel):
    bucket: str          # "0-30 days", "31-60 days", "61-90 days", "90+ days"
    count: int
    amount: Decimal


class RevenueBreakdown(BaseModel):
    """Month-by-month revenue for the current financial year."""
    month: str
    invoiced: Decimal
    collected: Decimal
    outstanding: Decimal


class CashFlowDashboardSchema(BaseModel):
    """
    Powers the main Virtual CFO Dashboard.
    All figures are for the current financial year unless noted.
    """
    as_of: datetime

    # ── Card 1: Revenue ───────────────────────
    total_revenue_ytd: Decimal            # Sum of paid invoices
    total_invoiced_ytd: Decimal           # Sum of all non-cancelled invoices
    revenue_collected_percent: float      # collected / invoiced × 100
    revenue_vs_last_month: Decimal        # +/- vs previous month's collections

    # ── Card 2: Receivables ───────────────────
    total_outstanding_receivables: Decimal
    overdue_receivables: Decimal          # Past due date and not fully paid
    receivables_aging: List[ReceivablesAgingBucket]

    # ── Card 3: GST Payable (from gst_service) ─
    gst_payable_current_month: Decimal
    gst_due_date: str                     # e.g. "20 Oct 2024"
    days_to_gst_due: int

    # ── Card 4: Payables ──────────────────────
    total_outstanding_payables: Decimal   # vendor outstanding balance
    overdue_payables: Decimal
    payables_due_next_7_days: Decimal

    # ── Card 5: Cash Position ─────────────────
    net_cash_position: Decimal            # receivables - payables (simplified)
    cash_runway_months: Optional[float]   # net_cash / avg monthly outflow

    # ── Revenue trend ─────────────────────────
    monthly_revenue: List[RevenueBreakdown]

    # ── Upcoming obligations ──────────────────
    invoices_due_next_30_days: int
    purchases_due_next_30_days: int
    total_due_next_30_days: Decimal

    # ── Active alerts summary ─────────────────
    active_alerts_count: int
    critical_alerts_count: int


# ─────────────────────────────────────────────
# ALERT SCHEMAS
# ─────────────────────────────────────────────

class AlertResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    alert_type: str
    severity: str
    title: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[UUID] = None
    is_read: bool
    read_at: Optional[datetime] = None
    dismissed: bool
    action_label: Optional[str] = None
    action_url: Optional[str] = None
    action_taken: bool
    ai_generated: bool
    ai_confidence: Optional[Decimal] = None
    recommendation: Optional[str] = None
    created_at: datetime


class AlertMarkReadSchema(BaseModel):
    alert_ids: List[UUID] = Field(..., min_length=1)


class AlertsSummarySchema(BaseModel):
    total: int
    unread: int
    critical: int
    high: int
    medium: int
    low: int
