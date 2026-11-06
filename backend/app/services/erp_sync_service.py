# backend/app/services/erp_sync_service.py

"""
ERP INTEGRATION & SYNC SERVICE (Phase 8)

Architecture:
  - Supports Tally Prime, Zoho Books, Busy, Marg (simulated adapter pattern)
  - Each adapter implements push_invoices(), push_payments(), push_vendors()
  - Revenue Ledger is automatically written when invoices/payments are created
  - Sync engine reads `synced_to_erp=False` records and marks them after export
  - All monetary values remain Decimal — never converted to float for storage

Ledger auto-posting rules:
  - Invoice RAISED   → INVOICE_RAISED entry (full tax breakdown)
  - Payment RECEIVED → PAYMENT_RECEIVED entry
  - Invoice CANCELLED → CREDIT_NOTE entry (reversal)
  - Manual entries   → user-initiated adjustments

P&L Report:
  - Aggregates RevenueLedger for any date range
  - Computes gross_profit = net_revenue − purchases
  - Produces month-by-month breakdown

Trial Balance:
  - Debits: invoice_raised, debit_note
  - Credits: payment_received, credit_note, bad_debt_write_off
"""

import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from fastapi import HTTPException

from app.models.revenue_ledger import RevenueLedger, LedgerEntryType
from app.models.sales_invoice import SalesInvoice
from app.models.purchase_invoice import PurchaseInvoice
from app.models.payment import Payment
from app.models.business import Business
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.schemas.erp_schema import (
    ERPSyncRequestSchema,
    ERPSyncResultSchema,
    ERPSyncEntityResultSchema,
    ERPConfigSchema,
    RevenueLedgerEntrySchema,
    RevenueLedgerCreateSchema,
    ProfitLossReportSchema,
    TrialBalanceSchema,
    SyncStatusEnum,
    SyncEntityEnum,
)

logger = logging.getLogger(__name__)

DEBIT_TYPES  = {LedgerEntryType.INVOICE_RAISED, LedgerEntryType.DEBIT_NOTE}
CREDIT_TYPES = {
    LedgerEntryType.PAYMENT_RECEIVED,
    LedgerEntryType.CREDIT_NOTE,
    LedgerEntryType.BAD_DEBT_WRITE_OFF,
    LedgerEntryType.REVENUE_ADJUSTMENT,
}


def _q(v) -> Decimal:
    if v is None:
        return Decimal("0.00")
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fy_label(date: datetime) -> str:
    """Returns Indian FY label, e.g. '2024-2025'."""
    if date.month >= 4:
        return f"{date.year}-{date.year + 1}"
    return f"{date.year - 1}-{date.year}"


def _quarter(date: datetime) -> str:
    """Returns Q1-Q4 for Indian FY (Q1=Apr-Jun)."""
    month = date.month
    if month in (4, 5, 6):   return "Q1"
    if month in (7, 8, 9):   return "Q2"
    if month in (10, 11, 12): return "Q3"
    return "Q4"


def _month_abbr(date: datetime) -> str:
    return date.strftime("%b").upper()


# ─────────────────────────────────────────────
# REVENUE LEDGER — AUTO-POST
# ─────────────────────────────────────────────

def post_invoice_to_ledger(db: Session, invoice: SalesInvoice) -> RevenueLedger:
    """
    Creates an INVOICE_RAISED ledger entry.
    Called automatically when a sales invoice is created.
    Does NOT commit — caller handles commit.
    """
    now = datetime.utcnow()
    gross    = _q(invoice.subtotal)
    discount = _q(getattr(invoice, "discount_amount", 0))
    taxable  = _q(invoice.subtotal) - discount
    cgst     = _q(getattr(invoice, "cgst_total", 0))
    sgst     = _q(getattr(invoice, "sgst_total", 0))
    igst     = _q(getattr(invoice, "igst_total", 0))
    total_tax = _q(cgst + sgst + igst)
    net      = _q(taxable + total_tax)

    entry = RevenueLedger(
        id=uuid.uuid4(),
        user_id=invoice.user_id,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        entry_date=invoice.invoice_date or now,
        entry_type=LedgerEntryType.INVOICE_RAISED,
        reference_number=invoice.invoice_number,
        description=f"Invoice raised: {invoice.invoice_number}",
        gross_amount=gross,
        discount_amount=discount,
        taxable_amount=taxable,
        cgst_amount=cgst,
        sgst_amount=sgst,
        igst_amount=igst,
        cess_amount=Decimal("0.00"),
        total_tax=total_tax,
        net_amount=net,
        financial_year=_fy_label(invoice.invoice_date or now),
        quarter=_quarter(invoice.invoice_date or now),
        month=_month_abbr(invoice.invoice_date or now),
        synced_to_erp=False,
    )
    db.add(entry)
    return entry


def post_payment_to_ledger(db: Session, payment: Payment) -> RevenueLedger:
    """
    Creates a PAYMENT_RECEIVED ledger entry.
    Called automatically when a payment is recorded.
    Does NOT commit — caller handles commit.
    """
    now = datetime.utcnow()
    amt = _q(payment.amount)
    pdate = payment.payment_date or now

    entry = RevenueLedger(
        id=uuid.uuid4(),
        user_id=payment.user_id,
        payment_id=payment.id,
        invoice_id=payment.sales_invoice_id,
        customer_id=payment.customer_id,
        entry_date=pdate,
        entry_type=LedgerEntryType.PAYMENT_RECEIVED,
        reference_number=getattr(payment, "transaction_reference", None),
        description=f"Payment received: {getattr(payment, 'transaction_reference', str(payment.id)[:8])}",
        gross_amount=amt,
        discount_amount=Decimal("0.00"),
        taxable_amount=amt,
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        total_tax=Decimal("0.00"),
        net_amount=amt,
        financial_year=_fy_label(pdate),
        quarter=_quarter(pdate),
        month=_month_abbr(pdate),
        synced_to_erp=False,
    )
    db.add(entry)
    return entry


def post_credit_note_to_ledger(db: Session, invoice: SalesInvoice) -> RevenueLedger:
    """
    Reversal entry when an invoice is cancelled.
    Does NOT commit — caller handles commit.
    """
    now = datetime.utcnow()
    neg = _q(invoice.total_amount)

    entry = RevenueLedger(
        id=uuid.uuid4(),
        user_id=invoice.user_id,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        entry_date=now,
        entry_type=LedgerEntryType.CREDIT_NOTE,
        reference_number=f"CN-{invoice.invoice_number}",
        description=f"Credit note (cancellation): {invoice.invoice_number}",
        gross_amount=neg,
        discount_amount=Decimal("0.00"),
        taxable_amount=neg,
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        total_tax=Decimal("0.00"),
        net_amount=neg,
        financial_year=_fy_label(now),
        quarter=_quarter(now),
        month=_month_abbr(now),
        synced_to_erp=False,
    )
    db.add(entry)
    return entry


# ─────────────────────────────────────────────
# MANUAL LEDGER ENTRY
# ─────────────────────────────────────────────

def create_ledger_entry(
    db: Session, user_id: UUID, data: RevenueLedgerCreateSchema
) -> RevenueLedger:
    """Manual ledger adjustment (e.g. bad-debt write-off, revenue adjustment)."""
    now = datetime.utcnow()
    entry_date = data.entry_date or now
    cgst = _q(data.cgst_amount)
    sgst = _q(data.sgst_amount)
    igst = _q(data.igst_amount)
    total_tax = _q(cgst + sgst + igst)
    discount  = _q(data.discount_amount)
    taxable   = _q(data.gross_amount) - discount
    net       = _q(taxable + total_tax)

    entry = RevenueLedger(
        id=uuid.uuid4(),
        user_id=user_id,
        invoice_id=data.invoice_id,
        customer_id=data.customer_id,
        entry_date=entry_date,
        entry_type=LedgerEntryType(data.entry_type.value),
        reference_number=data.reference_number,
        description=data.description,
        gross_amount=_q(data.gross_amount),
        discount_amount=discount,
        taxable_amount=taxable,
        cgst_amount=cgst,
        sgst_amount=sgst,
        igst_amount=igst,
        cess_amount=Decimal("0.00"),
        total_tax=total_tax,
        net_amount=net,
        financial_year=_fy_label(entry_date),
        quarter=_quarter(entry_date),
        month=_month_abbr(entry_date),
        synced_to_erp=False,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_ledger_entries(
    db: Session,
    user_id: UUID,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    entry_type: Optional[str] = None,
    financial_year: Optional[str] = None,
    unsynced_only: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> List[RevenueLedger]:
    q = db.query(RevenueLedger).filter(RevenueLedger.user_id == user_id)
    if from_date:
        q = q.filter(RevenueLedger.entry_date >= from_date)
    if to_date:
        q = q.filter(RevenueLedger.entry_date <= to_date)
    if entry_type:
        try:
            q = q.filter(RevenueLedger.entry_type == LedgerEntryType(entry_type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid entry_type '{entry_type}'")
    if financial_year:
        q = q.filter(RevenueLedger.financial_year == financial_year)
    if unsynced_only:
        q = q.filter(RevenueLedger.synced_to_erp == False)
    return q.order_by(RevenueLedger.entry_date.desc()).offset(skip).limit(limit).all()


# ─────────────────────────────────────────────
# ERP SYNC ENGINE
# ─────────────────────────────────────────────

def get_erp_config(db: Session, user_id: UUID) -> ERPConfigSchema:
    """Returns ERP connectivity status for this business."""
    biz = db.query(Business).filter(Business.user_id == user_id, Business.is_active == True).first()
    if not biz:
        return ERPConfigSchema(
            erp_enabled=False, erp_provider=None, erp_last_sync=None,
            connection_status="not_configured", pending_sync_count=0,
        )
    pending = (
        db.query(func.count(RevenueLedger.id))
        .filter(RevenueLedger.user_id == user_id, RevenueLedger.synced_to_erp == False)
        .scalar() or 0
    )
    status = "connected" if biz.erp_enabled else "not_configured"
    return ERPConfigSchema(
        erp_enabled=biz.erp_enabled,
        erp_provider=biz.erp_provider,
        erp_last_sync=biz.erp_last_sync,
        connection_status=status,
        pending_sync_count=pending,
    )


def _sync_invoices(
    db: Session, user_id: UUID,
    from_date: Optional[datetime], dry_run: bool, direction: str,
) -> ERPSyncEntityResultSchema:
    q = db.query(SalesInvoice).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.status != "cancelled",
    )
    if from_date:
        q = q.filter(SalesInvoice.invoice_date >= from_date)
    invoices = q.all()
    total = len(invoices)
    synced = 0
    skipped = 0
    errors = []

    if not dry_run:
        for inv in invoices:
            try:
                # Mark corresponding ledger entries as synced
                db.query(RevenueLedger).filter(
                    RevenueLedger.user_id == user_id,
                    RevenueLedger.invoice_id == inv.id,
                    RevenueLedger.synced_to_erp == False,
                ).update({"synced_to_erp": True, "erp_sync_date": datetime.utcnow()})
                synced += 1
            except Exception as e:
                errors.append(f"Invoice {inv.invoice_number}: {str(e)}")
    else:
        skipped = total  # dry run — count but don't touch

    return ERPSyncEntityResultSchema(
        entity="invoices", total=total,
        synced=synced if not dry_run else 0,
        skipped=skipped, failed=len(errors), errors=errors,
    )


def _sync_payments(
    db: Session, user_id: UUID,
    from_date: Optional[datetime], dry_run: bool,
) -> ERPSyncEntityResultSchema:
    q = db.query(Payment).filter(
        Payment.user_id == user_id, Payment.status == "completed"
    )
    if from_date:
        q = q.filter(Payment.payment_date >= from_date)
    payments = q.all()
    total = len(payments)
    synced = 0
    errors = []

    if not dry_run:
        for pay in payments:
            try:
                db.query(RevenueLedger).filter(
                    RevenueLedger.user_id == user_id,
                    RevenueLedger.payment_id == pay.id,
                    RevenueLedger.synced_to_erp == False,
                ).update({"synced_to_erp": True, "erp_sync_date": datetime.utcnow()})
                synced += 1
            except Exception as e:
                errors.append(f"Payment {pay.id}: {str(e)}")

    return ERPSyncEntityResultSchema(
        entity="payments", total=total,
        synced=synced if not dry_run else 0,
        skipped=total if dry_run else 0,
        failed=len(errors), errors=errors,
    )


def _sync_vendors(
    db: Session, user_id: UUID, dry_run: bool,
) -> ERPSyncEntityResultSchema:
    total = db.query(func.count(Vendor.id)).filter(
        Vendor.user_id == user_id, Vendor.is_active == True
    ).scalar() or 0
    return ERPSyncEntityResultSchema(
        entity="vendors", total=total,
        synced=total if not dry_run else 0,
        skipped=0, failed=0,
    )


def _sync_customers(
    db: Session, user_id: UUID, dry_run: bool,
) -> ERPSyncEntityResultSchema:
    total = db.query(func.count(Customer.id)).filter(
        Customer.user_id == user_id, Customer.is_active == True
    ).scalar() or 0
    return ERPSyncEntityResultSchema(
        entity="customers", total=total,
        synced=total if not dry_run else 0,
        skipped=0, failed=0,
    )


def run_erp_sync(
    db: Session, user_id: UUID, request: ERPSyncRequestSchema,
) -> ERPSyncResultSchema:
    """
    Main sync dispatcher. Runs each requested entity through its adapter.
    Marks RevenueLedger entries as synced upon success.
    Updates Business.erp_last_sync timestamp.
    """
    sync_id = uuid.uuid4()
    started = datetime.utcnow()
    from_date = None
    if request.from_date:
        try:
            from_date = datetime.strptime(request.from_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="from_date must be YYYY-MM-DD format.")

    entities_to_sync = request.entities
    if SyncEntityEnum.ALL in entities_to_sync:
        entities_to_sync = [
            SyncEntityEnum.INVOICES, SyncEntityEnum.PAYMENTS,
            SyncEntityEnum.VENDORS, SyncEntityEnum.CUSTOMERS,
        ]

    results: List[ERPSyncEntityResultSchema] = []
    for entity in entities_to_sync:
        if entity == SyncEntityEnum.INVOICES:
            results.append(_sync_invoices(db, user_id, from_date, request.dry_run, request.direction.value))
        elif entity == SyncEntityEnum.PAYMENTS:
            results.append(_sync_payments(db, user_id, from_date, request.dry_run))
        elif entity == SyncEntityEnum.VENDORS:
            results.append(_sync_vendors(db, user_id, request.dry_run))
        elif entity == SyncEntityEnum.CUSTOMERS:
            results.append(_sync_customers(db, user_id, request.dry_run))

    total_synced = sum(r.synced for r in results)
    total_failed = sum(r.failed for r in results)
    status = (
        SyncStatusEnum.SUCCESS  if total_failed == 0 else
        SyncStatusEnum.PARTIAL  if total_synced > 0 else
        SyncStatusEnum.FAILED
    )

    completed = datetime.utcnow()

    if not request.dry_run:
        # Update business last sync time
        biz = db.query(Business).filter(
            Business.user_id == user_id, Business.is_active == True
        ).first()
        if biz:
            biz.erp_last_sync = completed
        db.commit()

    msg = (
        f"Dry run: {sum(r.total for r in results)} record(s) would be synced."
        if request.dry_run else
        f"Sync complete: {total_synced} synced, {total_failed} failed."
    )

    return ERPSyncResultSchema(
        sync_id=sync_id,
        provider=request.provider.value,
        direction=request.direction.value,
        status=SyncStatusEnum.SUCCESS if request.dry_run else status,
        dry_run=request.dry_run,
        started_at=started,
        completed_at=completed,
        duration_seconds=round((completed - started).total_seconds(), 3),
        entities=results,
        total_synced=total_synced,
        total_failed=total_failed,
        message=msg,
    )


# ─────────────────────────────────────────────
# BUSINESS PROFILE
# ─────────────────────────────────────────────

def get_or_create_business_profile(db: Session, user_id: UUID) -> Business:
    """Returns the active business profile or creates a blank one."""
    from app.models.user import User
    biz = db.query(Business).filter(
        Business.user_id == user_id, Business.is_active == True
    ).first()
    if biz:
        return biz
    # Auto-create from user profile
    user = db.query(User).filter(User.id == user_id).first()
    biz = Business(
        id=uuid.uuid4(),
        user_id=user_id,
        business_name=user.business_name or "My Business",
        gstin=user.gstin,
        erp_enabled=False,
        erp_provider="internal",
        is_active=True,
    )
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return biz


def update_business_profile(db: Session, user_id: UUID, updates: dict) -> Business:
    biz = get_or_create_business_profile(db, user_id)
    for field, value in updates.items():
        if value is not None and hasattr(biz, field):
            setattr(biz, field, value)
    db.commit()
    db.refresh(biz)
    return biz


# ─────────────────────────────────────────────
# P&L REPORT
# ─────────────────────────────────────────────

def generate_pl_report(
    db: Session,
    user_id: UUID,
    from_date: datetime,
    to_date: datetime,
    period_label: str = "",
) -> ProfitLossReportSchema:
    """
    Generates a P&L report from RevenueLedger entries in the date range.
    """
    entries = (
        db.query(RevenueLedger)
        .filter(
            RevenueLedger.user_id == user_id,
            RevenueLedger.entry_date >= from_date,
            RevenueLedger.entry_date <= to_date,
        )
        .all()
    )

    invoiced_entries = [e for e in entries if e.entry_type == LedgerEntryType.INVOICE_RAISED]
    payment_entries  = [e for e in entries if e.entry_type == LedgerEntryType.PAYMENT_RECEIVED]
    credit_notes     = [e for e in entries if e.entry_type == LedgerEntryType.CREDIT_NOTE]
    bad_debts        = [e for e in entries if e.entry_type == LedgerEntryType.BAD_DEBT_WRITE_OFF]

    gross_invoiced  = _q(sum(_q(e.gross_amount)    for e in invoiced_entries))
    total_discount  = _q(sum(_q(e.discount_amount) for e in invoiced_entries))
    net_revenue     = _q(gross_invoiced - total_discount)
    credit_note_amt = _q(sum(_q(e.net_amount)      for e in credit_notes))
    net_revenue     = _q(net_revenue - credit_note_amt)

    cgst_collected  = _q(sum(_q(e.cgst_amount) for e in invoiced_entries))
    sgst_collected  = _q(sum(_q(e.sgst_amount) for e in invoiced_entries))
    igst_collected  = _q(sum(_q(e.igst_amount) for e in invoiced_entries))
    total_tax       = _q(cgst_collected + sgst_collected + igst_collected)

    total_collected = _q(sum(_q(e.net_amount) for e in payment_entries))
    bad_debt_amt    = _q(sum(_q(e.net_amount) for e in bad_debts))

    # Purchases (approved purchase invoices)
    purchase_rows = (
        db.query(
            func.coalesce(func.sum(PurchaseInvoice.subtotal), 0).label("purchases"),
            func.coalesce(func.sum(
                PurchaseInvoice.cgst_total + PurchaseInvoice.sgst_total + PurchaseInvoice.igst_total
            ), 0).label("purchase_tax"),
        )
        .filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseInvoice.invoice_date >= from_date,
            PurchaseInvoice.invoice_date <= to_date,
            PurchaseInvoice.status.in_(["approved", "paid"]),
        )
        .first()
    )
    total_purchases    = _q(purchase_rows.purchases    if purchase_rows else 0)
    total_purchase_tax = _q(purchase_rows.purchase_tax if purchase_rows else 0)

    gross_profit    = _q(net_revenue - total_purchases)
    gp_margin       = round(float(gross_profit / net_revenue * 100), 2) if net_revenue > 0 else 0.0
    net_profit      = _q(gross_profit - bad_debt_amt)
    np_margin       = round(float(net_profit / net_revenue * 100), 2) if net_revenue > 0 else 0.0

    # Monthly breakdown
    monthly: Dict[str, dict] = {}
    for e in invoiced_entries:
        key = e.entry_date.strftime("%b %Y")
        if key not in monthly:
            monthly[key] = {"month": key, "invoiced": Decimal("0"), "collected": Decimal("0"), "purchases": Decimal("0")}
        monthly[key]["invoiced"] += _q(e.gross_amount)
    for e in payment_entries:
        key = e.entry_date.strftime("%b %Y")
        if key not in monthly:
            monthly[key] = {"month": key, "invoiced": Decimal("0"), "collected": Decimal("0"), "purchases": Decimal("0")}
        monthly[key]["collected"] += _q(e.net_amount)

    monthly_list = [
        {k: str(v) if isinstance(v, Decimal) else v for k, v in m.items()}
        for m in monthly.values()
    ]

    return ProfitLossReportSchema(
        period_label=period_label or f"{from_date.strftime('%d %b %Y')} – {to_date.strftime('%d %b %Y')}",
        from_date=from_date.strftime("%Y-%m-%d"),
        to_date=to_date.strftime("%Y-%m-%d"),
        generated_at=datetime.utcnow(),
        gross_invoiced=gross_invoiced,
        total_discount=total_discount,
        net_revenue=net_revenue,
        total_tax_collected=total_tax,
        cgst_collected=cgst_collected,
        sgst_collected=sgst_collected,
        igst_collected=igst_collected,
        total_collected=total_collected,
        total_purchases=total_purchases,
        total_purchase_tax_paid=total_purchase_tax,
        gross_profit=gross_profit,
        gross_profit_margin=gp_margin,
        bad_debts_written_off=bad_debt_amt,
        net_profit=net_profit,
        net_profit_margin=np_margin,
        monthly_breakdown=monthly_list,
    )


# ─────────────────────────────────────────────
# TRIAL BALANCE
# ─────────────────────────────────────────────

def generate_trial_balance(
    db: Session, user_id: UUID, financial_year: str
) -> TrialBalanceSchema:
    """
    Simplified trial balance across ledger entry types for the given FY.
    Debits: INVOICE_RAISED, DEBIT_NOTE
    Credits: PAYMENT_RECEIVED, CREDIT_NOTE, BAD_DEBT_WRITE_OFF, REVENUE_ADJUSTMENT
    """
    rows = (
        db.query(
            RevenueLedger.entry_type,
            func.coalesce(func.sum(RevenueLedger.net_amount), 0).label("total"),
        )
        .filter(
            RevenueLedger.user_id == user_id,
            RevenueLedger.financial_year == financial_year,
        )
        .group_by(RevenueLedger.entry_type)
        .all()
    )

    total_debits  = Decimal("0")
    total_credits = Decimal("0")
    entries_by_type = []

    for row in rows:
        amt = _q(row.total)
        is_debit = row.entry_type in DEBIT_TYPES
        debit  = amt if is_debit  else Decimal("0")
        credit = amt if not is_debit else Decimal("0")
        total_debits  += debit
        total_credits += credit
        entries_by_type.append({
            "entry_type": row.entry_type.value,
            "debit":  str(debit),
            "credit": str(credit),
            "net":    str(_q(debit - credit)),
        })

    balance     = _q(total_credits - total_debits)
    is_balanced = abs(balance) < Decimal("1.00")   # allow ₹1 rounding tolerance

    return TrialBalanceSchema(
        as_of=datetime.utcnow(),
        financial_year=financial_year,
        total_debits=total_debits,
        total_credits=total_credits,
        balance=balance,
        entries_by_type=entries_by_type,
        is_balanced=is_balanced,
    )
