# backend/app/services/forecasting_service.py

"""
CASH FLOW FORECASTING SERVICE & VIRTUAL CFO DASHBOARD

Forecasting engine:
  - Uses 3–12 months of historical sales receipts and purchase payments
  - Applies: Moving Average (baseline) + Trend adjustment + Scenario multiplier
  - Generates per-period forecasts stored in cashflow_forecasts table
  - Attaches advisory notes and Virtual CFO recommendations when risk is detected

Dashboard engine:
  - Aggregates live data from: sales_invoices, payments, purchase_invoices, vendors
  - Produces the CashFlowDashboardSchema powering the frontend CFO dashboard
  - Receivables aging buckets (0-30, 31-60, 61-90, 90+)
  - Monthly revenue trend for current financial year

Architecture rule: Decimal everywhere, no float arithmetic on money.
"""

import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple
from uuid import UUID
from calendar import monthrange

from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.models.cashflow_forecast import CashflowForecast, ForecastType, ScenarioType
from app.models.sales_invoice import SalesInvoice
from app.models.payment import Payment
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.vendor import Vendor
from app.models.alert import Alert, AlertType, AlertSeverity
from app.schemas.forecast_schema import (
    ForecastRequestSchema,
    ForecastResponseSchema,
    ForecastListResponse,
    CashFlowDashboardSchema,
    ReceivablesAgingBucket,
    RevenueBreakdown,
    ForecastTypeEnum,
    ScenarioTypeEnum,
)
from app.services import alert_service

logger = logging.getLogger(__name__)

MODEL_VERSION = "v1.0"

# Scenario multipliers applied to baseline forecast
SCENARIO_MULTIPLIERS = {
    ScenarioType.OPTIMISTIC: Decimal("1.15"),   # +15% inflow, -10% outflow
    ScenarioType.BASELINE:   Decimal("1.00"),
    ScenarioType.PESSIMISTIC: Decimal("0.85"),  # -15% inflow, +10% outflow
}
OUTFLOW_SCENARIO_MULTIPLIERS = {
    ScenarioType.OPTIMISTIC:  Decimal("0.90"),
    ScenarioType.BASELINE:    Decimal("1.00"),
    ScenarioType.PESSIMISTIC: Decimal("1.10"),
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _q(v) -> Decimal:
    if v is None:
        return Decimal("0.00")
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_financial_year_bounds(ref_date: datetime) -> Tuple[datetime, datetime]:
    """Returns (start, end) of Indian financial year (Apr–Mar) containing ref_date."""
    if ref_date.month >= 4:
        fy_start = ref_date.replace(month=4, day=1, hour=0, minute=0, second=0, microsecond=0)
        fy_end   = ref_date.replace(year=ref_date.year + 1, month=3, day=31,
                                    hour=23, minute=59, second=59, microsecond=0)
    else:
        fy_start = ref_date.replace(year=ref_date.year - 1, month=4, day=1,
                                    hour=0, minute=0, second=0, microsecond=0)
        fy_end   = ref_date.replace(month=3, day=31, hour=23, minute=59, second=59, microsecond=0)
    return fy_start, fy_end


def _period_label(dt: datetime, forecast_type: ForecastType) -> str:
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    if forecast_type == ForecastType.MONTHLY:
        return f"{months[dt.month - 1]} {dt.year}"
    elif forecast_type == ForecastType.QUARTERLY:
        q = ((dt.month - 1) // 3) + 1
        return f"Q{q} {dt.year}"
    elif forecast_type == ForecastType.WEEKLY:
        return f"Week {dt.strftime('%V')} {dt.year}"
    else:  # DAILY
        return dt.strftime("%d %b %Y")


def _next_period_start(dt: datetime, forecast_type: ForecastType) -> datetime:
    """Advances dt by one period."""
    if forecast_type == ForecastType.MONTHLY:
        if dt.month == 12:
            return dt.replace(year=dt.year + 1, month=1, day=1)
        return dt.replace(month=dt.month + 1, day=1)
    elif forecast_type == ForecastType.QUARTERLY:
        months_ahead = 3
        m = dt.month + months_ahead
        y = dt.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        return dt.replace(year=y, month=m, day=1)
    elif forecast_type == ForecastType.WEEKLY:
        return dt + timedelta(weeks=1)
    else:
        return dt + timedelta(days=1)


def _period_end(start: datetime, forecast_type: ForecastType) -> datetime:
    """Returns the last moment of the period that starts at `start`."""
    next_s = _next_period_start(start, forecast_type)
    return next_s - timedelta(seconds=1)


# ─────────────────────────────────────────────
# HISTORICAL DATA EXTRACTION
# ─────────────────────────────────────────────

def _get_monthly_inflows(db: Session, user_id: UUID, months: int = 12) -> List[Decimal]:
    """
    Returns a list (oldest→newest) of monthly payment collections
    for the last `months` months.
    """
    cutoff = datetime.utcnow() - timedelta(days=30 * months)
    rows = (
        db.query(
            func.date_trunc("month", Payment.payment_date).label("month"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        )
        .filter(
            Payment.user_id == user_id,
            Payment.payment_date >= cutoff,
            Payment.status == "completed",
        )
        .group_by(func.date_trunc("month", Payment.payment_date))
        .order_by(func.date_trunc("month", Payment.payment_date))
        .all()
    )
    return [_q(r.total) for r in rows] or [Decimal("0.00")]


def _get_monthly_outflows(db: Session, user_id: UUID, months: int = 12) -> List[Decimal]:
    """
    Returns monthly purchase invoice totals (approved invoices = committed outflow).
    """
    cutoff = datetime.utcnow() - timedelta(days=30 * months)
    rows = (
        db.query(
            func.date_trunc("month", PurchaseInvoice.invoice_date).label("month"),
            func.coalesce(func.sum(PurchaseInvoice.total_amount), 0).label("total"),
        )
        .filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseInvoice.invoice_date >= cutoff,
            PurchaseInvoice.status.in_(["approved", "paid", "received"]),
        )
        .group_by(func.date_trunc("month", PurchaseInvoice.invoice_date))
        .order_by(func.date_trunc("month", PurchaseInvoice.invoice_date))
        .all()
    )
    return [_q(r.total) for r in rows] or [Decimal("0.00")]


# ─────────────────────────────────────────────
# STATISTICAL ENGINE
# ─────────────────────────────────────────────

def _moving_average(series: List[Decimal], window: int = 3) -> Decimal:
    """Simple moving average of last `window` values."""
    if not series:
        return Decimal("0.00")
    window = min(window, len(series))
    return _q(sum(series[-window:]) / window)


def _trend_adjustment(series: List[Decimal]) -> Decimal:
    """
    Linear trend: difference between first half avg and second half avg,
    applied as an additive offset to the moving average.
    Returns positive (growing) or negative (declining) adjustment per period.
    """
    if len(series) < 4:
        return Decimal("0.00")
    mid = len(series) // 2
    first_half_avg  = _q(sum(series[:mid]) / mid)
    second_half_avg = _q(sum(series[mid:]) / (len(series) - mid))
    return _q((second_half_avg - first_half_avg) / mid)


def _generate_advisory(
    predicted_net: Decimal,
    predicted_inflow: Decimal,
    predicted_outflow: Decimal,
    scenario: ScenarioType,
) -> Tuple[Optional[str], Optional[str], bool, Optional[str]]:
    """
    Generates advisory_notes, recommendation, alert_flag, and alert_severity
    based on forecast values.
    """
    alert_flag = False
    alert_severity = None
    notes = []
    recs = []

    if predicted_net < Decimal("0.00"):
        alert_flag = True
        alert_severity = "high"
        notes.append(
            f"Negative net cash flow of Rs. {abs(predicted_net):,.2f} predicted. "
            f"Outflows exceed inflows by {abs(predicted_net):,.2f}."
        )
        recs.append("Consider delaying discretionary purchases or accelerating collections from overdue customers.")

    elif predicted_net < predicted_inflow * Decimal("0.10"):
        alert_flag = True
        alert_severity = "medium"
        notes.append(
            f"Thin cash margin: net cash is only {float(predicted_net / predicted_inflow * 100):.1f}% of inflows."
        )
        recs.append("Review high-value payables and negotiate extended credit terms with vendors.")

    if scenario == ScenarioType.PESSIMISTIC and predicted_net < Decimal("0.00"):
        alert_severity = "critical"
        recs.append("Pessimistic scenario shows negative cash — evaluate emergency credit line or collections drive.")

    advisory_notes = " | ".join(notes) if notes else None
    recommendation = " | ".join(recs) if recs else "Cash flow looks healthy for this period."
    return advisory_notes, recommendation, alert_flag, alert_severity


# ─────────────────────────────────────────────
# FORECAST GENERATION
# ─────────────────────────────────────────────

def generate_forecast(
    db: Session,
    user_id: UUID,
    request: ForecastRequestSchema,
) -> ForecastListResponse:
    """
    Generates and saves `periods_ahead` forecast records.
    Uses moving average + trend on historical payment data.
    """
    ft = ForecastType(request.forecast_type.value)
    sc = ScenarioType(request.scenario.value)

    # Pull historical data (up to 12 months)
    inflow_history  = _get_monthly_inflows(db, user_id, months=12)
    outflow_history = _get_monthly_outflows(db, user_id, months=12)

    ma_inflow  = _moving_average(inflow_history, window=3)
    ma_outflow = _moving_average(outflow_history, window=3)
    trend_in   = _trend_adjustment(inflow_history)
    trend_out  = _trend_adjustment(outflow_history)

    in_mult  = SCENARIO_MULTIPLIERS[sc]
    out_mult = OUTFLOW_SCENARIO_MULTIPLIERS[sc]

    # Confidence degrades with fewer data points
    base_confidence = min(0.90, 0.50 + len(inflow_history) * 0.04)

    # Period start = first day of next period relative to today
    now = datetime.utcnow()
    if ft == ForecastType.MONTHLY:
        if now.month == 12:
            period_start = now.replace(year=now.year + 1, month=1, day=1,
                                       hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = now.replace(month=now.month + 1, day=1,
                                       hour=0, minute=0, second=0, microsecond=0)
    elif ft == ForecastType.QUARTERLY:
        curr_q_start_month = ((now.month - 1) // 3) * 3 + 1
        next_q_month = curr_q_start_month + 3
        if next_q_month > 12:
            period_start = now.replace(year=now.year + 1, month=next_q_month - 12, day=1,
                                       hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = now.replace(month=next_q_month, day=1,
                                       hour=0, minute=0, second=0, microsecond=0)
    elif ft == ForecastType.WEEKLY:
        period_start = (now + timedelta(days=7 - now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0)
    else:
        period_start = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)

    saved_forecasts: List[CashflowForecast] = []

    for i in range(request.periods_ahead):
        period_end = _period_end(period_start, ft)
        label = _period_label(period_start, ft)

        # Compound the trend: each period adds trend × (i+1)
        predicted_inflow  = _q((ma_inflow  + trend_in  * (i + 1)) * in_mult)
        predicted_outflow = _q((ma_outflow + trend_out * (i + 1)) * out_mult)
        predicted_inflow  = max(Decimal("0.00"), predicted_inflow)
        predicted_outflow = max(Decimal("0.00"), predicted_outflow)
        predicted_net     = _q(predicted_inflow - predicted_outflow)

        # Break inflow into components (heuristic proportions)
        sales_receipts = _q(predicted_inflow * Decimal("0.90"))
        purchase_pays  = _q(predicted_outflow * Decimal("0.60"))
        op_expenses    = _q(predicted_outflow * Decimal("0.20"))
        salary         = _q(predicted_outflow * Decimal("0.12"))
        tax_pays       = _q(predicted_outflow * Decimal("0.05"))
        loan_emis      = _q(predicted_outflow * Decimal("0.03"))

        advisory_notes, recommendation, alert_flag, alert_severity = _generate_advisory(
            predicted_net, predicted_inflow, predicted_outflow, sc
        )

        confidence = round(base_confidence - i * 0.03, 4)

        forecast = CashflowForecast(
            id=uuid.uuid4(),
            user_id=user_id,
            forecast_type=ft,
            scenario=sc,
            period_start=period_start,
            period_end=period_end,
            predicted_inflow=predicted_inflow,
            predicted_outflow=predicted_outflow,
            predicted_net=predicted_net,
            predicted_sales_receipts=sales_receipts,
            predicted_purchase_payments=purchase_pays,
            predicted_operating_expenses=op_expenses,
            predicted_salary_payouts=salary,
            predicted_tax_payments=tax_pays,
            predicted_loan_emis=loan_emis,
            confidence_score=_q(confidence),
            model_version=MODEL_VERSION,
            advisory_notes=advisory_notes,
            recommendation=recommendation,
            alert_generated=alert_flag,
            alert_severity=alert_severity,
        )
        db.add(forecast)

        # Auto-create alert if risk detected
        if alert_flag:
            sev = AlertSeverity(alert_severity) if alert_severity else AlertSeverity.MEDIUM
            alert_service.create_alert(
                db=db,
                user_id=user_id,
                alert_type=AlertType.LOW_CASH_BALANCE,
                severity=sev,
                title=f"Cash Flow Risk: {label}",
                message=advisory_notes or "Negative cash flow forecasted.",
                related_entity_type="forecast",
                related_entity_id=forecast.id,
                recommendation=recommendation,
                ai_generated=True,
                ai_confidence=_q(confidence),
            )

        period_start = _next_period_start(period_start, ft)
        saved_forecasts.append(forecast)

    db.commit()
    for f in saved_forecasts:
        db.refresh(f)

    total_in  = sum(_q(f.predicted_inflow)  for f in saved_forecasts)
    total_out = sum(_q(f.predicted_outflow) for f in saved_forecasts)
    total_net = sum(_q(f.predicted_net)     for f in saved_forecasts)

    return ForecastListResponse(
        scenario=request.scenario,
        forecast_type=request.forecast_type,
        periods=[ForecastResponseSchema.model_validate(f) for f in saved_forecasts],
        generated_at=datetime.utcnow(),
        summary={
            "total_predicted_inflow":  str(total_in),
            "total_predicted_outflow": str(total_out),
            "total_predicted_net":     str(total_net),
            "periods":                 len(saved_forecasts),
            "scenario":                sc.value,
        },
    )


def list_forecasts(
    db: Session,
    user_id: UUID,
    forecast_type: Optional[str] = None,
    scenario: Optional[str] = None,
    limit: int = 20,
) -> List[CashflowForecast]:
    q = db.query(CashflowForecast).filter(CashflowForecast.user_id == user_id)
    if forecast_type:
        q = q.filter(CashflowForecast.forecast_type == ForecastType(forecast_type))
    if scenario:
        q = q.filter(CashflowForecast.scenario == ScenarioType(scenario))
    return q.order_by(CashflowForecast.generated_at.desc()).limit(limit).all()


# ─────────────────────────────────────────────
# DASHBOARD AGGREGATOR
# ─────────────────────────────────────────────

def get_dashboard(db: Session, user_id: UUID) -> CashFlowDashboardSchema:
    """
    Aggregates all live data into a single dashboard snapshot.
    Reads from: sales_invoices, payments, purchase_invoices, vendors, alerts.
    """
    now = datetime.utcnow()
    fy_start, fy_end = _get_financial_year_bounds(now)

    # ── Card 1: Revenue YTD ───────────────────────────────────────────────
    total_invoiced_ytd = _q(
        db.query(func.coalesce(func.sum(SalesInvoice.total_amount), 0))
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.invoice_date >= fy_start,
            SalesInvoice.status != "cancelled",
        )
        .scalar()
    )

    total_revenue_ytd = _q(
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.user_id == user_id,
            Payment.payment_date >= fy_start,
            Payment.status == "completed",
        )
        .scalar()
    )

    revenue_collected_percent = (
        float(total_revenue_ytd / total_invoiced_ytd * 100)
        if total_invoiced_ytd > Decimal("0") else 0.0
    )

    # Last month vs current month collections
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first_of_last_month = (first_of_month - timedelta(days=1)).replace(day=1)

    this_month_collected = _q(
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.user_id == user_id,
            Payment.payment_date >= first_of_month,
            Payment.status == "completed",
        )
        .scalar()
    )
    last_month_collected = _q(
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.user_id == user_id,
            Payment.payment_date >= first_of_last_month,
            Payment.payment_date < first_of_month,
            Payment.status == "completed",
        )
        .scalar()
    )
    revenue_vs_last_month = _q(this_month_collected - last_month_collected)

    # ── Card 2: Receivables ───────────────────────────────────────────────
    total_outstanding_receivables = _q(
        db.query(func.coalesce(func.sum(SalesInvoice.amount_due), 0))
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.amount_due > 0,
            SalesInvoice.status.notin_(["cancelled", "paid"]),
        )
        .scalar()
    )

    overdue_invoices = (
        db.query(SalesInvoice)
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.amount_due > 0,
            SalesInvoice.due_date < now,
            SalesInvoice.status.notin_(["cancelled", "paid"]),
        )
        .all()
    )
    overdue_receivables = _q(sum(_q(i.amount_due) for i in overdue_invoices))

    # Aging buckets
    aging_buckets = _compute_receivables_aging(overdue_invoices + [
        i for i in db.query(SalesInvoice)
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.amount_due > 0,
            SalesInvoice.status.notin_(["cancelled", "paid"]),
        ).all()
    ], now)

    # ── Card 3: GST Payable ───────────────────────────────────────────────
    # Rough estimate: sum of (cgst + sgst + igst) on invoices this month minus ITC
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    gst_output_this_month = _q(
        db.query(
            func.coalesce(func.sum(
                SalesInvoice.cgst_total + SalesInvoice.sgst_total + SalesInvoice.igst_total
            ), 0)
        )
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.invoice_date >= month_start,
            SalesInvoice.status != "cancelled",
        )
        .scalar()
    )
    gst_itc_this_month = _q(
        db.query(
            func.coalesce(func.sum(
                PurchaseInvoice.cgst_total + PurchaseInvoice.sgst_total + PurchaseInvoice.igst_total
            ), 0)
        )
        .filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseInvoice.invoice_date >= month_start,
            PurchaseInvoice.status == "approved",
        )
        .scalar()
    )
    gst_payable = max(Decimal("0.00"), _q(gst_output_this_month - gst_itc_this_month))

    # GST due date: 20th of next month
    if now.month == 12:
        gst_due = now.replace(year=now.year + 1, month=1, day=20)
    else:
        gst_due = now.replace(month=now.month + 1, day=20)
    days_to_gst = max(0, (gst_due.date() - now.date()).days)
    gst_due_str = gst_due.strftime("%d %b %Y")

    # ── Card 4: Payables ──────────────────────────────────────────────────
    total_outstanding_payables = _q(
        db.query(func.coalesce(func.sum(Vendor.outstanding_balance), 0))
        .filter(Vendor.user_id == user_id, Vendor.is_active == True)
        .scalar()
    )

    overdue_purchase_invoices = (
        db.query(PurchaseInvoice)
        .filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseInvoice.amount_due > 0,
            PurchaseInvoice.due_date < now,
            PurchaseInvoice.status.notin_(["cancelled", "paid"]),
        )
        .all()
    )
    overdue_payables = _q(sum(_q(p.amount_due) for p in overdue_purchase_invoices))

    next_7 = now + timedelta(days=7)
    payables_due_soon = _q(
        db.query(func.coalesce(func.sum(PurchaseInvoice.amount_due), 0))
        .filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseInvoice.due_date >= now,
            PurchaseInvoice.due_date <= next_7,
            PurchaseInvoice.amount_due > 0,
            PurchaseInvoice.status.notin_(["cancelled", "paid"]),
        )
        .scalar()
    )

    # ── Card 5: Cash Position ─────────────────────────────────────────────
    net_cash_position = _q(total_outstanding_receivables - total_outstanding_payables)
    avg_monthly_outflow = _moving_average(_get_monthly_outflows(db, user_id, months=3))
    cash_runway = None
    if avg_monthly_outflow > Decimal("0"):
        cash_runway = round(float(net_cash_position / avg_monthly_outflow), 1)

    # ── Revenue trend (current FY, month by month) ────────────────────────
    monthly_revenue = _compute_monthly_revenue(db, user_id, fy_start, now)

    # ── Upcoming obligations ──────────────────────────────────────────────
    next_30 = now + timedelta(days=30)
    inv_due_count = (
        db.query(func.count(SalesInvoice.id))
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.due_date >= now,
            SalesInvoice.due_date <= next_30,
            SalesInvoice.status.notin_(["cancelled", "paid"]),
        )
        .scalar() or 0
    )
    pur_due_count = (
        db.query(func.count(PurchaseInvoice.id))
        .filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseInvoice.due_date >= now,
            PurchaseInvoice.due_date <= next_30,
            PurchaseInvoice.status.notin_(["cancelled", "paid"]),
        )
        .scalar() or 0
    )
    total_due_30 = _q(
        db.query(func.coalesce(func.sum(SalesInvoice.amount_due + 0), 0))
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.due_date <= next_30,
            SalesInvoice.amount_due > 0,
            SalesInvoice.status.notin_(["cancelled", "paid"]),
        )
        .scalar()
    )

    # ── Alert summary ─────────────────────────────────────────────────────
    active_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.user_id == user_id, Alert.dismissed == False)
        .scalar() or 0
    )
    critical_alerts = (
        db.query(func.count(Alert.id))
        .filter(
            Alert.user_id == user_id,
            Alert.dismissed == False,
            Alert.severity == AlertSeverity.CRITICAL,
        )
        .scalar() or 0
    )

    return CashFlowDashboardSchema(
        as_of=now,
        total_revenue_ytd=total_revenue_ytd,
        total_invoiced_ytd=total_invoiced_ytd,
        revenue_collected_percent=round(revenue_collected_percent, 2),
        revenue_vs_last_month=revenue_vs_last_month,
        total_outstanding_receivables=total_outstanding_receivables,
        overdue_receivables=overdue_receivables,
        receivables_aging=aging_buckets,
        gst_payable_current_month=gst_payable,
        gst_due_date=gst_due_str,
        days_to_gst_due=days_to_gst,
        total_outstanding_payables=total_outstanding_payables,
        overdue_payables=overdue_payables,
        payables_due_next_7_days=payables_due_soon,
        net_cash_position=net_cash_position,
        cash_runway_months=cash_runway,
        monthly_revenue=monthly_revenue,
        invoices_due_next_30_days=inv_due_count,
        purchases_due_next_30_days=pur_due_count,
        total_due_next_30_days=total_due_30,
        active_alerts_count=active_alerts,
        critical_alerts_count=critical_alerts,
    )


def _compute_receivables_aging(
    invoices: List[SalesInvoice], now: datetime
) -> List[ReceivablesAgingBucket]:
    """Classifies outstanding invoices into aging buckets."""
    buckets = {
        "0-30 days":  {"count": 0, "amount": Decimal("0.00")},
        "31-60 days": {"count": 0, "amount": Decimal("0.00")},
        "61-90 days": {"count": 0, "amount": Decimal("0.00")},
        "90+ days":   {"count": 0, "amount": Decimal("0.00")},
    }
    seen_ids = set()
    for inv in invoices:
        if inv.id in seen_ids:
            continue
        seen_ids.add(inv.id)
        if _q(inv.amount_due) <= Decimal("0"):
            continue
        ref = inv.due_date or inv.invoice_date
        age = (now - ref).days if ref else 0
        amt = _q(inv.amount_due)
        if age <= 30:
            buckets["0-30 days"]["count"] += 1
            buckets["0-30 days"]["amount"] += amt
        elif age <= 60:
            buckets["31-60 days"]["count"] += 1
            buckets["31-60 days"]["amount"] += amt
        elif age <= 90:
            buckets["61-90 days"]["count"] += 1
            buckets["61-90 days"]["amount"] += amt
        else:
            buckets["90+ days"]["count"] += 1
            buckets["90+ days"]["amount"] += amt

    return [
        ReceivablesAgingBucket(bucket=k, count=v["count"], amount=v["amount"])
        for k, v in buckets.items()
    ]


def _compute_monthly_revenue(
    db: Session, user_id: UUID, fy_start: datetime, now: datetime
) -> List[RevenueBreakdown]:
    """Month-by-month invoiced vs collected for the current financial year."""
    MONTHS = ["Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar"]
    result = []
    cursor = fy_start.replace(day=1)

    while cursor <= now:
        m_start = cursor
        last_day = monthrange(cursor.year, cursor.month)[1]
        m_end = cursor.replace(day=last_day, hour=23, minute=59, second=59)

        invoiced = _q(
            db.query(func.coalesce(func.sum(SalesInvoice.total_amount), 0))
            .filter(
                SalesInvoice.user_id == user_id,
                SalesInvoice.invoice_date >= m_start,
                SalesInvoice.invoice_date <= m_end,
                SalesInvoice.status != "cancelled",
            )
            .scalar()
        )
        collected = _q(
            db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.user_id == user_id,
                Payment.payment_date >= m_start,
                Payment.payment_date <= m_end,
                Payment.status == "completed",
            )
            .scalar()
        )
        outstanding = max(Decimal("0.00"), _q(invoiced - collected))

        label = f"{MONTHS[cursor.month - 1] if cursor.month in range(1,13) else cursor.strftime('%b')} {cursor.year}"
        result.append(RevenueBreakdown(
            month=label,
            invoiced=invoiced,
            collected=collected,
            outstanding=outstanding,
        ))

        # Advance to next month
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1, day=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1, day=1)

    return result
