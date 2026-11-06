# backend/app/api/payments/routes.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.payment_schema import PaymentCreateSchema, PaymentResponseSchema
from app.schemas.billing_schema import (
    InvoiceResponseSchema,
    InvoiceListResponseSchema
)
from app.services.payment_service import (
    record_payment,
    get_payment,
    list_payments,
    send_invoice,
    cancel_invoice,
    list_invoices,
    mark_overdue_invoices,
)

router = APIRouter(tags=["Payments & Invoice Lifecycle"])


# ─────────────────────────────────────────────
# PAYMENT ENDPOINTS
# ─────────────────────────────────────────────

@router.post(
    "/payments",
    response_model=PaymentResponseSchema,
    status_code=201,
    summary="Record a payment against an invoice"
)
def create_payment(
    payload: PaymentCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Records a payment.

    For customer paying your sales invoice:
    - Set sales_invoice_id and customer_id
    - Set direction = "incoming"

    Invoice status updates automatically:
    - Partial payment → stays SENT
    - Full payment → auto-marked PAID
    """
    return record_payment(db, payload, current_user.id)


@router.get(
    "/payments",
    response_model=list[PaymentResponseSchema],
    summary="List all payments"
)
def list_payments_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return list_payments(db, current_user.id, skip, limit)


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponseSchema,
    summary="Get a single payment"
)
def get_payment_endpoint(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    payment = get_payment(db, payment_id, current_user.id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


# ─────────────────────────────────────────────
# INVOICE LIFECYCLE ENDPOINTS
# ─────────────────────────────────────────────

@router.get(
    "/invoices",
    response_model=list[InvoiceListResponseSchema],
    summary="List all invoices with optional status filter"
)
def list_invoices_endpoint(
    status: Optional[str] = Query(
        default=None,
        description="Filter by status: draft | sent | paid | overdue | cancelled"
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return list_invoices(db, current_user.id, status, skip, limit)


@router.patch(
    "/invoices/{invoice_id}/send",
    response_model=InvoiceListResponseSchema,
    summary="Mark a DRAFT invoice as SENT"
)
def send_invoice_endpoint(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Transitions invoice: DRAFT → SENT
    Only SENT invoices can receive payments.
    """
    return send_invoice(db, invoice_id, current_user.id)


@router.patch(
    "/invoices/{invoice_id}/cancel",
    response_model=InvoiceListResponseSchema,
    summary="Cancel an invoice"
)
def cancel_invoice_endpoint(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cancels a DRAFT or SENT invoice.
    PAID invoices cannot be cancelled.
    """
    return cancel_invoice(db, invoice_id, current_user.id)


@router.post(
    "/invoices/check-overdue",
    summary="Scan and mark overdue invoices"
)
def check_overdue_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Scans all SENT invoices past their due_date.
    Marks them as OVERDUE automatically.
    In production this runs as a daily scheduled job.
    """
    count = mark_overdue_invoices(db, current_user.id)
    return {
        "message": f"{count} invoice(s) marked as OVERDUE",
        "count": count
    }