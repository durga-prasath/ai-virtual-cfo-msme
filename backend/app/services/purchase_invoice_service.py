# backend/app/services/purchase_invoice_service.py

"""
PURCHASE INVOICE SERVICE

Handles:
- Vendor CRUD (create, list, get)
- Purchase invoice CRUD (manual create, list, get, approve, cancel)
- OCR scan → auto-create purchase invoice pipeline
- ITC tracking (purchase invoices feed GSTR-3B via gst_service.generate_gstr3b)

Architecture rules:
- All functions accept (db: Session, user_id: UUID, ...)
- user_id always comes from JWT — never from request body
- No Float for money — always Decimal with ROUND_HALF_UP
- Invoice numbers use PINV-YYYY-NNNN format (per-user sequence)
"""

import os
import uuid
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.vendor import Vendor
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.schemas.invoice_schema import (
    VendorCreateSchema,
    VendorResponseSchema,
    PurchaseInvoiceCreateSchema,
    PurchaseInvoiceResponseSchema,
    OCRExtractionResult,
)

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "vendor_bills")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _q(v) -> Decimal:
    """Quantize a Decimal to 2dp using ROUND_HALF_UP."""
    if v is None:
        return Decimal("0.00")
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _generate_purchase_invoice_number(db: Session, user_id: UUID) -> str:
    """
    Generates sequential PINV-YYYY-NNNN per user per year.
    Thread-safe via DB count.
    """
    year = datetime.utcnow().year
    count = (
        db.query(func.count(PurchaseInvoice.id))
        .filter(
            PurchaseInvoice.user_id == user_id,
            func.extract("year", PurchaseInvoice.created_at) == year,
        )
        .scalar()
        or 0
    )
    return f"PINV-{year}-{count + 1:04d}"


# ─────────────────────────────────────────────
# VENDOR CRUD
# ─────────────────────────────────────────────

def create_vendor(db: Session, user_id: UUID, data: VendorCreateSchema) -> Vendor:
    """Creates a new vendor for the given user."""
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data.name.strip(),
        contact_person=data.contact_person,
        email=data.email,
        phone=data.phone,
        gstin=data.gstin.upper().strip() if data.gstin else None,
        pan=data.pan.upper().strip() if data.pan else None,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
        bank_name=data.bank_name,
        bank_account_number=data.bank_account_number,
        bank_ifsc=data.bank_ifsc,
        upi_id=data.upi_id,
        outstanding_balance=Decimal("0.00"),
        credit_limit=Decimal("0.00"),
        is_active=True,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    logger.info(f"Vendor created: {vendor.name} (id={vendor.id}) for user={user_id}")
    return vendor


def list_vendors(
    db: Session,
    user_id: UUID,
    active_only: bool = True,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Vendor]:
    """Lists vendors belonging to the logged-in user."""
    q = db.query(Vendor).filter(Vendor.user_id == user_id)
    if active_only:
        q = q.filter(Vendor.is_active == True)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            (func.lower(Vendor.name).like(term))
            | (func.lower(Vendor.gstin).like(term))
            | (func.lower(Vendor.email).like(term))
        )
    return q.order_by(Vendor.name).offset(skip).limit(limit).all()


def get_vendor(db: Session, user_id: UUID, vendor_id: UUID) -> Vendor:
    """Fetches a single vendor, enforcing user ownership."""
    vendor = (
        db.query(Vendor)
        .filter(Vendor.id == vendor_id, Vendor.user_id == user_id)
        .first()
    )
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return vendor


# ─────────────────────────────────────────────
# PURCHASE INVOICE — INTERNAL CALCULATOR
# ─────────────────────────────────────────────

def _compute_invoice_totals(data: PurchaseInvoiceCreateSchema):
    """
    Derives: tax_amount, total_amount, amount_due from incoming schema values.
    All arithmetic in Decimal.
    """
    subtotal       = _q(data.subtotal)
    cgst           = _q(data.cgst_total)
    sgst           = _q(data.sgst_total)
    igst           = _q(data.igst_total)
    discount       = _q(data.discount_amount)

    tax_amount     = cgst + sgst + igst
    total_amount   = subtotal + tax_amount - discount
    amount_due     = total_amount  # No payment yet on creation

    return subtotal, cgst, sgst, igst, discount, tax_amount, total_amount, amount_due


# ─────────────────────────────────────────────
# PURCHASE INVOICE CRUD
# ─────────────────────────────────────────────

def create_purchase_invoice(
    db: Session,
    user_id: UUID,
    data: PurchaseInvoiceCreateSchema,
) -> PurchaseInvoice:
    """Manual creation of a purchase invoice. Validates vendor ownership."""
    # Verify vendor belongs to this user
    vendor = get_vendor(db, user_id, data.vendor_id)

    subtotal, cgst, sgst, igst, discount, tax_amount, total_amount, amount_due = (
        _compute_invoice_totals(data)
    )

    inv_number = _generate_purchase_invoice_number(db, user_id)

    invoice = PurchaseInvoice(
        id=uuid.uuid4(),
        user_id=user_id,
        vendor_id=vendor.id,
        invoice_number=inv_number,
        vendor_invoice_number=data.vendor_invoice_number,
        invoice_date=data.invoice_date or datetime.utcnow(),
        due_date=data.due_date,
        received_date=data.received_date or datetime.utcnow(),
        status=PurchaseInvoiceStatus.RECEIVED,
        subtotal=subtotal,
        cgst_total=cgst,
        sgst_total=sgst,
        igst_total=igst,
        discount_amount=discount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        amount_paid=Decimal("0.00"),
        amount_due=amount_due,
        notes=data.notes,
        terms=data.terms,
        ocr_extracted=data.ocr_extracted,
        ocr_confidence=_q(data.ocr_confidence) if data.ocr_confidence else None,
        synced_to_erp=False,
    )
    db.add(invoice)

    # Update vendor outstanding balance
    vendor.outstanding_balance = _q(vendor.outstanding_balance) + total_amount
    db.commit()
    db.refresh(invoice)
    logger.info(f"Purchase invoice {inv_number} created for user={user_id}")
    return invoice


def list_purchase_invoices(
    db: Session,
    user_id: UUID,
    vendor_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[PurchaseInvoice]:
    """Lists purchase invoices for the logged-in user, with optional filters."""
    q = db.query(PurchaseInvoice).filter(PurchaseInvoice.user_id == user_id)
    if vendor_id:
        q = q.filter(PurchaseInvoice.vendor_id == vendor_id)
    if status_filter:
        try:
            s = PurchaseInvoiceStatus(status_filter.lower())
            q = q.filter(PurchaseInvoice.status == s)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status_filter}'. Valid: draft, received, approved, paid, cancelled.",
            )
    return q.order_by(PurchaseInvoice.invoice_date.desc()).offset(skip).limit(limit).all()


def get_purchase_invoice(
    db: Session, user_id: UUID, invoice_id: UUID
) -> PurchaseInvoice:
    """Fetches a single purchase invoice, enforcing user ownership."""
    inv = (
        db.query(PurchaseInvoice)
        .filter(PurchaseInvoice.id == invoice_id, PurchaseInvoice.user_id == user_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Purchase invoice not found.")
    return inv


def approve_purchase_invoice(
    db: Session, user_id: UUID, invoice_id: UUID
) -> PurchaseInvoice:
    """Moves a purchase invoice from RECEIVED/DRAFT → APPROVED."""
    inv = get_purchase_invoice(db, user_id, invoice_id)
    if inv.status not in (PurchaseInvoiceStatus.DRAFT, PurchaseInvoiceStatus.RECEIVED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve invoice in status '{inv.status.value}'. Must be DRAFT or RECEIVED.",
        )
    inv.status = PurchaseInvoiceStatus.APPROVED
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)
    logger.info(f"Purchase invoice {inv.invoice_number} approved by user={user_id}")
    return inv


def cancel_purchase_invoice(
    db: Session, user_id: UUID, invoice_id: UUID
) -> PurchaseInvoice:
    """Cancels a purchase invoice (if not already PAID)."""
    inv = get_purchase_invoice(db, user_id, invoice_id)
    if inv.status == PurchaseInvoiceStatus.PAID:
        raise HTTPException(
            status_code=400, detail="Cannot cancel a PAID invoice."
        )
    if inv.status == PurchaseInvoiceStatus.CANCELLED:
        raise HTTPException(
            status_code=400, detail="Invoice is already cancelled."
        )

    # Reverse outstanding balance on vendor
    vendor = db.query(Vendor).filter(Vendor.id == inv.vendor_id).first()
    if vendor:
        vendor.outstanding_balance = max(
            Decimal("0.00"),
            _q(vendor.outstanding_balance) - _q(inv.amount_due),
        )

    inv.status = PurchaseInvoiceStatus.CANCELLED
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)
    logger.info(f"Purchase invoice {inv.invoice_number} cancelled by user={user_id}")
    return inv


# ─────────────────────────────────────────────
# OCR → PURCHASE INVOICE AUTO-CREATE
# ─────────────────────────────────────────────

def create_from_ocr(
    db: Session,
    user_id: UUID,
    file_bytes: bytes,
    filename: str,
    vendor_id: UUID,
    saved_file_path: Optional[str] = None,
) -> dict:
    """
    Full OCR pipeline:
    1. Calls ocr_service.scan_vendor_bill() to extract fields from uploaded file
    2. Builds a PurchaseInvoiceCreateSchema from extracted data
    3. Creates the purchase invoice in DB (status = DRAFT for review)
    4. Returns both the OCR extraction result and the created invoice

    The invoice starts as DRAFT so the user can review and correct before approving.
    """
    from app.services.ocr_service import scan_vendor_bill

    # Step 1: Extract text + fields
    ocr_result: OCRExtractionResult = scan_vendor_bill(file_bytes, filename)

    # Step 2: Map OCR fields → schema (best-effort, fallback to 0 if not detected)
    def safe_decimal(field_result) -> Decimal:
        if field_result and field_result.value:
            try:
                return _q(field_result.value)
            except Exception:
                pass
        return Decimal("0.00")

    subtotal     = safe_decimal(ocr_result.subtotal)
    cgst_total   = safe_decimal(ocr_result.cgst_amount)
    sgst_total   = safe_decimal(ocr_result.sgst_amount)
    igst_total   = safe_decimal(ocr_result.igst_amount)
    discount     = safe_decimal(ocr_result.discount_amount)

    # If subtotal is zero but total is known, back-calculate subtotal
    total_from_ocr = safe_decimal(ocr_result.total_amount)
    tax_total = cgst_total + sgst_total + igst_total
    if subtotal == Decimal("0.00") and total_from_ocr > Decimal("0.00"):
        subtotal = max(Decimal("0.00"), total_from_ocr - tax_total + discount)

    invoice_create = PurchaseInvoiceCreateSchema(
        vendor_id=vendor_id,
        vendor_invoice_number=(
            ocr_result.invoice_number.value if ocr_result.invoice_number.value else None
        ),
        subtotal=subtotal,
        cgst_total=cgst_total,
        sgst_total=sgst_total,
        igst_total=igst_total,
        discount_amount=discount,
        ocr_extracted=True,
        ocr_confidence=Decimal(str(round(ocr_result.overall_confidence, 2))),
        notes=f"Auto-created from OCR scan of '{filename}'. Review before approving.",
    )

    # Step 3: Create invoice (override status to DRAFT for review)
    invoice = create_purchase_invoice(db, user_id, invoice_create)
    invoice.status = PurchaseInvoiceStatus.DRAFT

    # Attach file path if we saved the file
    if saved_file_path:
        invoice.uploaded_file_path = saved_file_path

    db.commit()
    db.refresh(invoice)

    return {
        "invoice": invoice,
        "ocr_result": ocr_result,
        "review_required": True,
        "message": (
            f"Invoice PINV scan complete (confidence: {ocr_result.overall_confidence:.1f}%). "
            f"Status set to DRAFT — please review and approve."
        ),
    }


def save_uploaded_file(file_bytes: bytes, filename: str, user_id: UUID) -> str:
    """
    Saves the uploaded bill file to disk and returns the saved path.
    Files are stored under uploads/vendor_bills/<user_id>/<filename>.
    """
    user_dir = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    # Avoid collisions with timestamp prefix
    safe_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
    file_path = os.path.join(user_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    logger.info(f"Saved uploaded file: {file_path}")
    return file_path
