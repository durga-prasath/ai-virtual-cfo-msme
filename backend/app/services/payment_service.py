# backend/app/services/payment_service.py

"""
PAYMENT SERVICE LAYER

Handles payment recording and invoice lifecycle management.

Key business rules:
1. When a payment is recorded against a sales invoice:
   - amount_paid increases
   - amount_due decreases
   - If amount_due reaches 0 → invoice status = PAID
   - If amount_due > 0 → invoice stays SENT (partial payment)

2. A payment cannot exceed the invoice's amount_due.

3. Invoice must be in SENT status to accept payments.
   DRAFT invoices cannot be paid — they must be sent first.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
import logging

from fastapi import HTTPException, status

from app.models.payment import Payment, PaymentDirection, PaymentStatus
from app.models.sales_invoice import SalesInvoice, InvoiceStatus
from app.schemas.payment_schema import PaymentCreateSchema

logger = logging.getLogger(__name__)


def round_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────
# PAYMENT RECORDING
# ─────────────────────────────────────────────

def record_payment(db: Session, data: PaymentCreateSchema, user_id: UUID) -> Payment:
    """
    Records a payment and updates the linked invoice automatically.

    Transaction flow:
    1. Validate the invoice exists and belongs to this user
    2. Validate payment amount doesn't exceed amount_due
    3. Create Payment record
    4. Update invoice: amount_paid, amount_due
    5. If fully paid → set invoice status to PAID
    6. Commit everything as one transaction
    """

    invoice = None

    # ── Validate sales invoice if provided ──
    if data.sales_invoice_id:
        invoice = db.query(SalesInvoice).filter(
            SalesInvoice.id == data.sales_invoice_id,
            SalesInvoice.user_id == user_id
        ).first()

        if not invoice:
            raise HTTPException(
                status_code=404,
                detail="Invoice not found"
            )

        # Only SENT or OVERDUE invoices can receive payments
        # DRAFT invoices must be sent first
        if invoice.status not in [InvoiceStatus.SENT, InvoiceStatus.OVERDUE]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invoice is '{invoice.status.value}'. "
                       f"Only SENT or OVERDUE invoices can receive payments. "
                       f"Use PATCH /invoices/{{id}}/send to send the invoice first."
            )

        # Validate payment amount doesn't exceed what's owed
        amount_due = round_decimal(invoice.amount_due)
        payment_amount = round_decimal(data.amount)

        if payment_amount > amount_due:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment amount ₹{payment_amount} exceeds "
                       f"amount due ₹{amount_due}. "
                       f"Maximum payable: ₹{amount_due}"
            )

    # ── Create payment record ──
    payment = Payment(
        id=uuid4(),
        user_id=user_id,
        sales_invoice_id=data.sales_invoice_id,
        purchase_invoice_id=data.purchase_invoice_id,
        customer_id=data.customer_id,
        vendor_id=data.vendor_id,
        amount=round_decimal(data.amount),
        payment_method=data.payment_method.value,
        direction=data.direction.value,
        status=PaymentStatus.COMPLETED,        # Assume completed on recording
        payment_date=data.payment_date or datetime.utcnow(),
        transaction_reference=data.transaction_reference,
        utr_number=data.utr_number,
        upi_transaction_id=data.upi_transaction_id,
        bank_reference=data.bank_reference,
        notes=data.notes,
    )
    db.add(payment)

    # ── Update invoice financials ──
    if invoice:
        new_amount_paid = round_decimal(
            Decimal(str(invoice.amount_paid)) + round_decimal(data.amount)
        )
        new_amount_due = round_decimal(
            Decimal(str(invoice.total_amount)) - new_amount_paid
        )

        invoice.amount_paid = new_amount_paid
        invoice.amount_due = new_amount_due

        # Auto-mark as PAID if fully settled
        if new_amount_due <= Decimal('0.00'):
            invoice.status = InvoiceStatus.PAID
            invoice.paid_date = datetime.utcnow()
            invoice.payment_method = data.payment_method.value
            logger.info(f"Invoice {invoice.invoice_number} marked as PAID")
        else:
            logger.info(
                f"Partial payment on {invoice.invoice_number}. "
                f"Remaining: ₹{new_amount_due}"
            )

    try:
        # ── Auto-post to Revenue Ledger ──
        try:
            from app.services.erp_sync_service import post_payment_to_ledger
            post_payment_to_ledger(db, payment)
        except Exception as ledger_err:
            logger.warning(f"Ledger auto-post failed (non-fatal): {ledger_err}")

        db.commit()
        db.refresh(payment)
        logger.info(f"Payment recorded: {payment.amount} via {payment.payment_method}")
        return payment
    except Exception as e:
        db.rollback()
        logger.error(f"Payment recording failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to record payment")


def get_payment(db: Session, payment_id: UUID, user_id: UUID) -> Optional[Payment]:
    return db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.user_id == user_id
    ).first()


def list_payments(
    db: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 50
):
    return db.query(Payment).filter(
        Payment.user_id == user_id
    ).order_by(Payment.created_at.desc()).offset(skip).limit(limit).all()


# ─────────────────────────────────────────────
# INVOICE LIFECYCLE
# ─────────────────────────────────────────────

def send_invoice(db: Session, invoice_id: UUID, user_id: UUID) -> SalesInvoice:
    """
    Marks a DRAFT invoice as SENT.

    Business rule: Only DRAFT invoices can be sent.
    Once sent, the invoice can receive payments.
    """
    invoice = db.query(SalesInvoice).filter(
        SalesInvoice.id == invoice_id,
        SalesInvoice.user_id == user_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only DRAFT invoices can be sent. "
                   f"Current status: {invoice.status.value}"
        )

    invoice.status = InvoiceStatus.SENT
    logger.info(f"Invoice {invoice.invoice_number} marked as SENT")

    try:
        db.commit()
        db.refresh(invoice)
        return invoice
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update invoice")


def cancel_invoice(db: Session, invoice_id: UUID, user_id: UUID) -> SalesInvoice:
    """
    Cancels an invoice.
    PAID invoices cannot be cancelled — they must be refunded instead.
    """
    invoice = db.query(SalesInvoice).filter(
        SalesInvoice.id == invoice_id,
        SalesInvoice.user_id == user_id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(
            status_code=400,
            detail="PAID invoices cannot be cancelled. Process a refund instead."
        )

    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(
            status_code=400,
            detail="Invoice is already cancelled."
        )

    invoice.status = InvoiceStatus.CANCELLED
    logger.info(f"Invoice {invoice.invoice_number} cancelled")

    try:
        db.commit()
        db.refresh(invoice)
        return invoice
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to cancel invoice")


def list_invoices(
    db: Session,
    user_id: UUID,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """
    Lists invoices with optional status filter.
    Example: list_invoices(db, user_id, status_filter="overdue")
    """
    query = db.query(SalesInvoice).filter(SalesInvoice.user_id == user_id)

    if status_filter:
        query = query.filter(SalesInvoice.status == status_filter)

    return query.order_by(SalesInvoice.created_at.desc()).offset(skip).limit(limit).all()


def mark_overdue_invoices(db: Session, user_id: UUID) -> int:
    """
    Scans all SENT invoices past their due_date and marks them OVERDUE.
    Returns count of invoices updated.

    In production this would be called by a scheduler (e.g. daily cron job).
    """
    now = datetime.utcnow()

    overdue_invoices = db.query(SalesInvoice).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.status == InvoiceStatus.SENT,
        SalesInvoice.due_date < now,
        SalesInvoice.due_date.isnot(None)
    ).all()

    count = 0
    for invoice in overdue_invoices:
        invoice.status = InvoiceStatus.OVERDUE
        count += 1

    if count > 0:
        try:
            db.commit()
            logger.info(f"Marked {count} invoices as OVERDUE")
        except Exception as e:
            db.rollback()
            raise

    return count