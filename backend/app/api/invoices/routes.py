# backend/app/api/invoices/routes.py

"""
PURCHASE INVOICES & VENDOR API ROUTES

Prefix: /api/v1/purchases  (mounted in main.py)

Vendor endpoints:
  POST   /api/v1/purchases/vendors           — Create vendor
  GET    /api/v1/purchases/vendors           — List vendors
  GET    /api/v1/purchases/vendors/{id}      — Get vendor

Purchase invoice endpoints:
  POST   /api/v1/purchases/invoices          — Create purchase invoice (manual)
  GET    /api/v1/purchases/invoices          — List purchase invoices
  GET    /api/v1/purchases/invoices/{id}     — Get single invoice
  POST   /api/v1/purchases/invoices/{id}/approve  — Approve invoice
  POST   /api/v1/purchases/invoices/{id}/cancel   — Cancel invoice

OCR endpoint:
  POST   /api/v1/purchases/invoices/scan     — Upload vendor bill → OCR → DRAFT invoice
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.invoice_schema import (
    VendorCreateSchema,
    VendorResponseSchema,
    PurchaseInvoiceCreateSchema,
    PurchaseInvoiceResponseSchema,
    OCRExtractionResult,
)
from app.services import purchase_invoice_service

router = APIRouter(prefix="/purchases", tags=["Purchase Invoices & Vendors"])

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
MAX_FILE_SIZE_MB = 15


# ─────────────────────────────────────────────
# VENDOR ROUTES
# ─────────────────────────────────────────────

@router.post("/vendors", response_model=VendorResponseSchema, status_code=201)
def create_vendor(
    data: VendorCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data.user_id = None  # Server always sets user_id from JWT
    vendor = purchase_invoice_service.create_vendor(db, current_user.id, data)
    return vendor


@router.get("/vendors", response_model=list[VendorResponseSchema])
def list_vendors(
    active_only: bool = Query(True, description="Return only active vendors"),
    search: Optional[str] = Query(None, description="Search by name, GSTIN, or email"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return purchase_invoice_service.list_vendors(
        db, current_user.id, active_only=active_only, search=search, skip=skip, limit=limit
    )


@router.get("/vendors/{vendor_id}", response_model=VendorResponseSchema)
def get_vendor(
    vendor_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return purchase_invoice_service.get_vendor(db, current_user.id, vendor_id)


# ─────────────────────────────────────────────
# PURCHASE INVOICE ROUTES
# ─────────────────────────────────────────────

@router.post("/invoices", response_model=PurchaseInvoiceResponseSchema, status_code=201)
def create_purchase_invoice(
    data: PurchaseInvoiceCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual creation of a purchase invoice."""
    data.user_id = None  # Server-side only
    return purchase_invoice_service.create_purchase_invoice(db, current_user.id, data)


@router.get("/invoices", response_model=list[PurchaseInvoiceResponseSchema])
def list_purchase_invoices(
    vendor_id: Optional[UUID] = Query(None, description="Filter by vendor"),
    status: Optional[str] = Query(None, description="Filter by status: draft/received/approved/paid/cancelled"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return purchase_invoice_service.list_purchase_invoices(
        db, current_user.id, vendor_id=vendor_id, status_filter=status, skip=skip, limit=limit
    )


@router.get("/invoices/{invoice_id}", response_model=PurchaseInvoiceResponseSchema)
def get_purchase_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return purchase_invoice_service.get_purchase_invoice(db, current_user.id, invoice_id)


@router.post("/invoices/{invoice_id}/approve", response_model=PurchaseInvoiceResponseSchema)
def approve_purchase_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move invoice from DRAFT/RECEIVED → APPROVED (eligible for ITC claim)."""
    return purchase_invoice_service.approve_purchase_invoice(db, current_user.id, invoice_id)


@router.post("/invoices/{invoice_id}/cancel", response_model=PurchaseInvoiceResponseSchema)
def cancel_purchase_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a purchase invoice (reverses vendor outstanding balance)."""
    return purchase_invoice_service.cancel_purchase_invoice(db, current_user.id, invoice_id)


# ─────────────────────────────────────────────
# OCR SCAN ROUTE
# ─────────────────────────────────────────────

@router.post("/invoices/scan", status_code=201)
async def scan_vendor_bill(
    vendor_id: UUID = Form(..., description="Vendor UUID the bill belongs to"),
    file: UploadFile = File(..., description="PDF or image of the vendor bill"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a vendor bill (PDF/image) → OCR extraction → auto-create DRAFT purchase invoice.

    Returns:
    - invoice: the created PurchaseInvoice (status=DRAFT, needs review & approve)
    - ocr_result: all extracted fields with per-field confidence scores
    - review_required: always True (user must verify before approving)
    - message: human-readable summary
    """
    import os

    # Validate file extension
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and size-check
    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum allowed: {MAX_FILE_SIZE_MB} MB.",
        )

    # Save file to disk
    saved_path = purchase_invoice_service.save_uploaded_file(
        file_bytes, file.filename, current_user.id
    )

    # Run OCR pipeline and create invoice
    try:
        result = purchase_invoice_service.create_from_ocr(
            db=db,
            user_id=current_user.id,
            file_bytes=file_bytes,
            filename=file.filename,
            vendor_id=vendor_id,
            saved_file_path=saved_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Serialize for response
    invoice_data = PurchaseInvoiceResponseSchema.model_validate(result["invoice"])
    ocr_data = result["ocr_result"]

    return {
        "invoice": invoice_data.model_dump(),
        "ocr_result": ocr_data.model_dump(),
        "review_required": result["review_required"],
        "message": result["message"],
    }
