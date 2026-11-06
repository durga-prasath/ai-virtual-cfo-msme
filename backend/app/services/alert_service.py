# backend/app/services/alert_service.py

"""
SMART ALERT ENGINE

Handles:
- Create alert (called by other services: forecasting, billing, GST)
- List alerts (unread/all, by type/severity)
- Mark alerts as read (bulk)
- Dismiss alerts
- Alert summary (counts by severity)
- Auto-scan: generate alerts for overdue invoices, upcoming GST deadlines,
  revenue drops, and vendor risk — called by GET /dashboard
"""

import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from app.models.alert import Alert, AlertType, AlertSeverity
from app.models.sales_invoice import SalesInvoice
from app.models.purchase_invoice import PurchaseInvoice
from app.models.gst_record import GSTRecord, FilingStatus
from app.schemas.forecast_schema import AlertResponseSchema, AlertsSummarySchema

logger = logging.getLogger(__name__)


def _q(v) -> Decimal:
    if v is None:
        return Decimal("0.00")
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────────

def create_alert(
    db: Session,
    user_id: UUID,
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    message: str,
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[UUID] = None,
    action_label: Optional[str] = None,
    action_url: Optional[str] = None,
    recommendation: Optional[str] = None,
    ai_generated: bool = False,
    ai_confidence: Optional[Decimal] = None,
) -> Alert:
    """Creates and persists a single alert. Does NOT commit — caller handles commit."""
    alert = Alert(
        id=uuid.uuid4(),
        user_id=user_id,
        alert_type=alert_type,
        severity=severity,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        action_label=action_label,
        action_url=action_url,
        recommendation=recommendation,
        ai_generated=ai_generated,
        ai_confidence=ai_confidence,
        is_read=False,
        dismissed=False,
        action_taken=False,
    )
    db.add(alert)
    return alert


# ─────────────────────────────────────────────
# LIST & QUERY
# ─────────────────────────────────────────────

def list_alerts(
    db: Session,
    user_id: UUID,
    unread_only: bool = False,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    include_dismissed: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> List[Alert]:
    q = db.query(Alert).filter(Alert.user_id == user_id)
    if unread_only:
        q = q.filter(Alert.is_read == False)
    if not include_dismissed:
        q = q.filter(Alert.dismissed == False)
    if severity:
        try:
            q = q.filter(Alert.severity == AlertSeverity(severity.lower()))
        except ValueError:
            raise HTTPException(status_code=400,
                detail=f"Invalid severity '{severity}'. Valid: low, medium, high, critical.")
    if alert_type:
        try:
            q = q.filter(Alert.alert_type == AlertType(alert_type.lower()))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid alert_type '{alert_type}'.")
    return q.order_by(Alert.created_at.desc()).offset(skip).limit(limit).all()


def get_alerts_summary(db: Session, user_id: UUID) -> AlertsSummarySchema:
    base = db.query(Alert).filter(Alert.user_id == user_id, Alert.dismissed == False)
    total   = base.count()
    unread  = base.filter(Alert.is_read == False).count()
    critical= base.filter(Alert.severity == AlertSeverity.CRITICAL).count()
    high    = base.filter(Alert.severity == AlertSeverity.HIGH).count()
    medium  = base.filter(Alert.severity == AlertSeverity.MEDIUM).count()
    low     = base.filter(Alert.severity == AlertSeverity.LOW).count()
    return AlertsSummarySchema(
        total=total, unread=unread,
        critical=critical, high=high, medium=medium, low=low,
    )


# ─────────────────────────────────────────────
# MARK READ / DISMISS
# ─────────────────────────────────────────────

def mark_alerts_read(
    db: Session,
    user_id: UUID,
    alert_ids: List[UUID],
) -> int:
    """Marks specific alerts as read. Returns count updated."""
    now = datetime.utcnow()
    updated = (
        db.query(Alert)
        .filter(
            Alert.user_id == user_id,
            Alert.id.in_(alert_ids),
            Alert.is_read == False,
        )
        .all()
    )
    for a in updated:
        a.is_read = True
        a.read_at = now
    db.commit()
    return len(updated)


def mark_all_read(db: Session, user_id: UUID) -> int:
    """Marks ALL unread alerts for this user as read."""
    now = datetime.utcnow()
    alerts = (
        db.query(Alert)
        .filter(Alert.user_id == user_id, Alert.is_read == False)
        .all()
    )
    for a in alerts:
        a.is_read = True
        a.read_at = now
    db.commit()
    return len(alerts)


def dismiss_alert(db: Session, user_id: UUID, alert_id: UUID) -> Alert:
    """Dismisses a single alert (soft-delete equivalent)."""
    alert = (
        db.query(Alert)
        .filter(Alert.id == alert_id, Alert.user_id == user_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.dismissed = True
    alert.dismissed_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert


# ─────────────────────────────────────────────
# AUTO-SCAN ENGINE
# ─────────────────────────────────────────────

def run_alert_scan(db: Session, user_id: UUID) -> int:
    """
    Scans business data and generates alerts for detected risks.
    Called automatically when the dashboard is fetched.
    Idempotent: will not create duplicate alerts for the same entity on the same day.

    Returns: count of new alerts created.
    """
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    new_count = 0

    # ── 1. Overdue Sales Invoices ─────────────────────────────────────────
    overdue_invoices = (
        db.query(SalesInvoice)
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.due_date < now,
            SalesInvoice.amount_due > 0,
            SalesInvoice.status.notin_(["cancelled", "paid"]),
        )
        .all()
    )
    for inv in overdue_invoices:
        # Don't re-alert for the same invoice today
        exists = (
            db.query(Alert)
            .filter(
                Alert.user_id == user_id,
                Alert.alert_type == AlertType.INVOICE_OVERDUE,
                Alert.related_entity_id == inv.id,
                Alert.created_at >= today_start,
            )
            .first()
        )
        if not exists:
            days_overdue = (now - inv.due_date).days
            sev = AlertSeverity.HIGH if days_overdue > 30 else AlertSeverity.MEDIUM
            create_alert(
                db=db,
                user_id=user_id,
                alert_type=AlertType.INVOICE_OVERDUE,
                severity=sev,
                title=f"Invoice {inv.invoice_number} Overdue by {days_overdue} Days",
                message=(
                    f"Invoice {inv.invoice_number} for Rs. {_q(inv.amount_due):,.2f} "
                    f"was due on {inv.due_date.strftime('%d %b %Y')} and is {days_overdue} days overdue."
                ),
                related_entity_type="sales_invoice",
                related_entity_id=inv.id,
                action_label="View Invoice",
                action_url=f"/invoices/{inv.id}",
                recommendation="Send a payment reminder to the customer immediately.",
            )
            new_count += 1

    # ── 2. Invoices Due in Next 7 Days ────────────────────────────────────
    next_7 = now + timedelta(days=7)
    upcoming_invoices = (
        db.query(SalesInvoice)
        .filter(
            SalesInvoice.user_id == user_id,
            SalesInvoice.due_date >= now,
            SalesInvoice.due_date <= next_7,
            SalesInvoice.amount_due > 0,
            SalesInvoice.status.notin_(["cancelled", "paid"]),
        )
        .all()
    )
    for inv in upcoming_invoices:
        exists = (
            db.query(Alert)
            .filter(
                Alert.user_id == user_id,
                Alert.alert_type == AlertType.PAYMENT_DUE,
                Alert.related_entity_id == inv.id,
                Alert.created_at >= today_start,
            )
            .first()
        )
        if not exists:
            days_left = (inv.due_date - now).days
            create_alert(
                db=db,
                user_id=user_id,
                alert_type=AlertType.PAYMENT_DUE,
                severity=AlertSeverity.LOW,
                title=f"Invoice {inv.invoice_number} Due in {days_left} Day(s)",
                message=(
                    f"Invoice {inv.invoice_number} for Rs. {_q(inv.amount_due):,.2f} "
                    f"is due on {inv.due_date.strftime('%d %b %Y')}."
                ),
                related_entity_type="sales_invoice",
                related_entity_id=inv.id,
                action_label="View Invoice",
                action_url=f"/invoices/{inv.id}",
            )
            new_count += 1

    # ── 3. GST Filing Due Alert ───────────────────────────────────────────
    # Alert if GSTR-3B filing is due within 7 days (20th of next month)
    if now.month == 12:
        gst_due = now.replace(year=now.year + 1, month=1, day=20)
    else:
        gst_due = now.replace(month=now.month + 1, day=20)

    days_to_gst = (gst_due.date() - now.date()).days
    if 0 < days_to_gst <= 7:
        period_str = now.strftime("%m-%Y")
        # Check if GSTR-3B is already filed for this period
        already_filed = (
            db.query(GSTRecord)
            .filter(
                GSTRecord.user_id == user_id,
                GSTRecord.return_period == period_str,
                GSTRecord.return_type == "gstr3b",
                GSTRecord.status == FilingStatus.FILED,
            )
            .first()
        )
        already_alerted = (
            db.query(Alert)
            .filter(
                Alert.user_id == user_id,
                Alert.alert_type == AlertType.GST_FILING_DUE,
                Alert.created_at >= today_start,
            )
            .first()
        )
        if not already_filed and not already_alerted:
            sev = AlertSeverity.HIGH if days_to_gst <= 3 else AlertSeverity.MEDIUM
            create_alert(
                db=db,
                user_id=user_id,
                alert_type=AlertType.GST_FILING_DUE,
                severity=sev,
                title=f"GSTR-3B Due in {days_to_gst} Day(s)",
                message=(
                    f"Your GSTR-3B for {period_str} is due on "
                    f"{gst_due.strftime('%d %b %Y')}. Ensure it is filed to avoid late fees."
                ),
                action_label="File GST Return",
                action_url="/gst/file",
                recommendation="Review your tax liability report before filing.",
            )
            new_count += 1

    # ── 4. Overdue Purchase Payments ─────────────────────────────────────
    overdue_purchases = (
        db.query(PurchaseInvoice)
        .filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseInvoice.due_date < now,
            PurchaseInvoice.amount_due > 0,
            PurchaseInvoice.status.notin_(["cancelled", "paid"]),
        )
        .all()
    )
    for pinv in overdue_purchases:
        exists = (
            db.query(Alert)
            .filter(
                Alert.user_id == user_id,
                Alert.alert_type == AlertType.VENDOR_RISK_ALERT,
                Alert.related_entity_id == pinv.id,
                Alert.created_at >= today_start,
            )
            .first()
        )
        if not exists:
            days_overdue = (now - pinv.due_date).days
            create_alert(
                db=db,
                user_id=user_id,
                alert_type=AlertType.VENDOR_RISK_ALERT,
                severity=AlertSeverity.MEDIUM,
                title=f"Vendor Payment Overdue by {days_overdue} Days",
                message=(
                    f"Purchase invoice {pinv.invoice_number} for Rs. {_q(pinv.amount_due):,.2f} "
                    f"was due on {pinv.due_date.strftime('%d %b %Y')} — {days_overdue} days overdue."
                ),
                related_entity_type="purchase_invoice",
                related_entity_id=pinv.id,
                action_label="View Purchase Invoice",
                action_url=f"/purchases/invoices/{pinv.id}",
                recommendation="Contact the vendor to arrange payment and prevent supply disruption.",
            )
            new_count += 1

    if new_count > 0:
        db.commit()
        logger.info(f"Alert scan for user={user_id}: {new_count} new alerts created.")

    return new_count
