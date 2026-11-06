# backend/app/api/gst/routes.py

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List, Dict, Any

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.gst_record import ReturnType
from app.schemas.gst_schema import (
    GSTR1ReportResponse,
    GSTR3BReportResponse,
    GSTReconciliationResponse,
    TaxLiabilitySummaryResponse,
    GSTFileReturnRequest,
    GSTRecordResponseSchema,
)
from app.services.gst_service import (
    generate_gstr1,
    generate_gstr3b,
    reconcile_gst,
    get_tax_liability,
    file_return,
    list_gst_records,
    get_gst_portal_json,
)

router = APIRouter(prefix="/gst", tags=["GST Reports & Compliance"])


def resolve_return_period(
    return_period: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> str:
    if return_period and return_period.strip():
        return return_period.strip()
    if month is not None and year is not None:
        return f"{month:02d}-{year}"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Missing return period. Provide 'return_period' (MM-YYYY) or both 'month' and 'year'."
    )


# ─────────────────────────────────────────────
# GSTR-1 OUTWARD SUPPLIES ENDPOINTS
# ─────────────────────────────────────────────

@router.get(
    "/gstr1",
    response_model=GSTR1ReportResponse,
    summary="Generate GSTR-1 Outward Supplies Report"
)
def get_gstr1_report_endpoint(
    return_period: Optional[str] = Query(None, description="Format: MM-YYYY (e.g. 04-2026)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month (1-12)"),
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Year (e.g. 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generates GSTR-1 outward supplies return:
    - B2B registered supplies
    - B2C Large (> ₹2.5L inter-state unregistered)
    - B2C Small supplies summary by state and GST rate
    - HSN/SAC summary aggregation
    - Document issuance sequence & count
    """
    period = resolve_return_period(return_period, month, year)
    return generate_gstr1(db, current_user.id, period)


@router.get(
    "/gstr1/json",
    summary="Get official Government GST Portal JSON for GSTR-1"
)
def get_gstr1_portal_json_endpoint(
    return_period: Optional[str] = Query(None, description="Format: MM-YYYY (e.g. 04-2026)"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the government portal offline-tool compliant JSON payload
    ready for direct upload to the GST portal.
    """
    period = resolve_return_period(return_period, month, year)
    return get_gst_portal_json(db, current_user.id, ReturnType.GSTR1, period)


# ─────────────────────────────────────────────
# GSTR-3B MONTHLY SUMMARY ENDPOINTS
# ─────────────────────────────────────────────

@router.get(
    "/gstr3b",
    response_model=GSTR3BReportResponse,
    summary="Generate GSTR-3B Monthly Return Summary"
)
def get_gstr3b_report_endpoint(
    return_period: Optional[str] = Query(None, description="Format: MM-YYYY (e.g. 04-2026)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month (1-12)"),
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Year (e.g. 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generates GSTR-3B monthly return:
    - Table 3.1 Outward supplies tax liability
    - Table 3.2 Inter-state unregistered supplies
    - Table 4.0 Eligible Input Tax Credit (ITC) from purchase invoices
    - Table 5.1 Late fee and interest calculation if past deadline
    - Table 6.1 Payment of tax with automated ITC utilization
    """
    period = resolve_return_period(return_period, month, year)
    return generate_gstr3b(db, current_user.id, period)


@router.get(
    "/gstr3b/json",
    summary="Get official Government GST Portal JSON for GSTR-3B"
)
def get_gstr3b_portal_json_endpoint(
    return_period: Optional[str] = Query(None, description="Format: MM-YYYY (e.g. 04-2026)"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the government portal offline-tool compliant JSON payload for GSTR-3B.
    """
    period = resolve_return_period(return_period, month, year)
    return get_gst_portal_json(db, current_user.id, ReturnType.GSTR3B, period)


# ─────────────────────────────────────────────
# RECONCILIATION & EXECUTIVE TAX LIABILITY
# ─────────────────────────────────────────────

@router.get(
    "/reconciliation",
    response_model=GSTReconciliationResponse,
    summary="Perform GST Reconciliation & Discrepancy Audit"
)
def get_gst_reconciliation_endpoint(
    return_period: Optional[str] = Query(None, description="Format: MM-YYYY (e.g. 04-2026)"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Audits discrepancies between:
    - GSTR-1 outward taxable supplies vs GSTR-3B outward supplies
    - Purchase invoices ITC vs claimed ITC
    - Missing HSN codes or draft invoice omissions
    """
    period = resolve_return_period(return_period, month, year)
    return reconcile_gst(db, current_user.id, period)


@router.get(
    "/liability",
    response_model=TaxLiabilitySummaryResponse,
    summary="Get Real-Time Period Tax Liability & Balance"
)
def get_tax_liability_endpoint(
    return_period: Optional[str] = Query(None, description="Format: MM-YYYY (e.g. 04-2026)"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Provides real-time tax balance overview (Gross tax, available ITC, net cash tax payable).
    Directly powers Dashboard Card 3 ("GST Payable").
    """
    period = resolve_return_period(return_period, month, year)
    return get_tax_liability(db, current_user.id, period)



# ─────────────────────────────────────────────
# FILING LIFECYCLE & HISTORICAL RECORDS
# ─────────────────────────────────────────────

@router.post(
    "/file",
    response_model=GSTRecordResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Mark a GST Return as Filed"
)
def file_gst_return_endpoint(
    payload: GSTFileReturnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Transitions return status from READY_TO_FILE/PENDING to FILED.
    Records statutory acknowledgement number and amount paid.
    """
    return file_return(db, current_user.id, payload)


@router.get(
    "/records",
    response_model=List[GSTRecordResponseSchema],
    summary="List GST Filing History & Statuses"
)
def list_gst_records_endpoint(
    return_period: Optional[str] = Query(None, description="Optional filter by MM-YYYY"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lists all filed, ready-to-file, and pending GST records for the authenticated user.
    """
    period = return_period.strip() if (return_period and return_period.strip()) else (f"{month:02d}-{year}" if month and year else None)
    return list_gst_records(db, current_user.id, period)

