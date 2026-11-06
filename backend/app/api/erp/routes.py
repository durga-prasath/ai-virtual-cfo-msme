# backend/app/api/erp/routes.py

"""
ERP INTEGRATION & REVENUE LEDGER API ROUTES (Phase 8)

Prefix: /api/v1/erp  (mounted in main.py)

Business profile:
  GET   /erp/business            — Get (or auto-create) business profile
  PATCH /erp/business            — Update business profile / ERP config

ERP sync:
  GET   /erp/config              — ERP connectivity status + pending sync count
  POST  /erp/sync                — Trigger sync (push/pull, all or specific entities)

Revenue ledger:
  GET   /erp/ledger              — List ledger entries (filter by date, type, FY)
  POST  /erp/ledger              — Manual adjustment entry

Financial reports:
  GET   /erp/reports/pl          — P&L report (from_date, to_date)
  GET   /erp/reports/trial       — Trial balance for a financial year
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.erp_schema import (
    BusinessProfileSchema,
    BusinessProfileUpdateSchema,
    ERPSyncRequestSchema,
    ERPSyncResultSchema,
    ERPConfigSchema,
    RevenueLedgerEntrySchema,
    RevenueLedgerCreateSchema,
    ProfitLossReportSchema,
    TrialBalanceSchema,
)
from app.services import erp_sync_service, tally_xml_service

router = APIRouter(prefix="/erp", tags=["ERP Integration & Revenue Ledger"])



# ─────────────────────────────────────────────
# BUSINESS PROFILE
# ─────────────────────────────────────────────

@router.get("/business", response_model=BusinessProfileSchema)
def get_business_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the business profile. Auto-creates from user account if not set up."""
    return erp_sync_service.get_or_create_business_profile(db, current_user.id)


@router.patch("/business", response_model=BusinessProfileSchema)
def update_business_profile(
    payload: BusinessProfileUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update business details and/or ERP provider configuration."""
    updates = payload.model_dump(exclude_none=True)
    if "erp_provider" in updates:
        updates["erp_provider"] = updates["erp_provider"].value
    return erp_sync_service.update_business_profile(db, current_user.id, updates)


# ─────────────────────────────────────────────
# ERP CONFIG & SYNC
# ─────────────────────────────────────────────

@router.get("/config", response_model=ERPConfigSchema)
def get_erp_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns ERP connection status and count of pending-sync ledger records."""
    return erp_sync_service.get_erp_config(db, current_user.id)


@router.post("/sync", response_model=ERPSyncResultSchema)
def run_erp_sync(
    request: ERPSyncRequestSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger an ERP sync.
    - provider: tally | zoho | busy | marg | internal
    - direction: push (platform → ERP) | pull (ERP → platform)
    - entities: invoices, payments, vendors, customers, ledger, all
    - dry_run: preview without actually syncing
    Marks matching RevenueLedger entries as synced_to_erp = True.
    """
    return erp_sync_service.run_erp_sync(db, current_user.id, request)


# ─────────────────────────────────────────────
# REVENUE LEDGER
# ─────────────────────────────────────────────

@router.get("/ledger", response_model=List[RevenueLedgerEntrySchema])
def list_ledger(
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    entry_type: Optional[str] = Query(None),
    financial_year: Optional[str] = Query(None, description="e.g. 2024-2025"),
    unsynced_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List revenue ledger entries. Supports date range, type, FY and sync-status filters."""
    fd = datetime.strptime(from_date, "%Y-%m-%d") if from_date else None
    td = datetime.strptime(to_date,   "%Y-%m-%d").replace(hour=23, minute=59, second=59) if to_date else None
    return erp_sync_service.list_ledger_entries(
        db, current_user.id,
        from_date=fd, to_date=td,
        entry_type=entry_type, financial_year=financial_year,
        unsynced_only=unsynced_only, skip=skip, limit=limit,
    )


@router.post("/ledger", response_model=RevenueLedgerEntrySchema, status_code=201)
def create_ledger_entry(
    payload: RevenueLedgerCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a manual ledger adjustment entry.
    Use for: bad-debt write-offs, revenue adjustments, debit notes, credit notes.
    """
    return erp_sync_service.create_ledger_entry(db, current_user.id, payload)


# ─────────────────────────────────────────────
# FINANCIAL REPORTS
# ─────────────────────────────────────────────

@router.get("/reports/pl", response_model=ProfitLossReportSchema)
def get_pl_report(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date:   str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Profit & Loss report for the specified date range.
    Aggregates from the RevenueLedger.
    Includes: gross revenue, discounts, net revenue, GST collected,
    purchases, gross profit, bad debts, net profit, and monthly breakdown.
    """
    fd = datetime.strptime(from_date, "%Y-%m-%d")
    td = datetime.strptime(to_date,   "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    label = f"{fd.strftime('%d %b %Y')} to {td.strftime('%d %b %Y')}"
    return erp_sync_service.generate_pl_report(db, current_user.id, fd, td, label)


@router.get("/reports/trial", response_model=TrialBalanceSchema)
def get_trial_balance(
    financial_year: str = Query(..., description="e.g. 2024-2025"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Simplified trial balance for the given Indian financial year (Apr–Mar).
    Debits: INVOICE_RAISED, DEBIT_NOTE
    Credits: PAYMENT_RECEIVED, CREDIT_NOTE, BAD_DEBT_WRITE_OFF
    """
    return erp_sync_service.generate_trial_balance(db, current_user.id, financial_year)


# ─────────────────────────────────────────────
# TALLY XML EXPORT ROUTES (PHASE 9)
# ─────────────────────────────────────────────

@router.get("/tally/summary")
def get_tally_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns total counts of records ready for Tally XML export."""
    return tally_xml_service.get_tally_export_summary(db, current_user.id)


@router.get("/tally/export/invoices")
def export_tally_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates Tally-compatible XML voucher package for sales invoices."""
    xml_data = tally_xml_service.export_sales_invoices_to_tally_xml(db, current_user.id)
    return Response(
        content=xml_data,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="tally_sales_vouchers.xml"'},
    )


@router.get("/tally/export/purchases")
def export_tally_purchases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates Tally-compatible XML voucher package for purchase bills."""
    xml_data = tally_xml_service.export_purchase_invoices_to_tally_xml(db, current_user.id)
    return Response(
        content=xml_data,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="tally_purchase_vouchers.xml"'},
    )


@router.get("/tally/export/payments")
def export_tally_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates Tally-compatible XML voucher package for payment receipts."""
    xml_data = tally_xml_service.export_payments_to_tally_xml(db, current_user.id)
    return Response(
        content=xml_data,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="tally_receipt_vouchers.xml"'},
    )

