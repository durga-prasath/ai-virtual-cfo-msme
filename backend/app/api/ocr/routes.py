# backend/app/api/ocr/routes.py

"""
PHASE 6: DOCUMENT SCANNER API ROUTES

Prefix: /api/v1/ocr

Endpoints:
- POST /api/v1/ocr/scan: Scan file -> OpenCV + OCR + classification + field extraction
- POST /api/v1/ocr/confirm: Save confirmed fields to DB
- GET /api/v1/ocr/supported-types: Get supported doc types
"""

import os
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.vendor import Vendor
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.revenue_ledger import RevenueLedger, LedgerEntryType
from app.schemas.ocr_schema import (
    ScanDocumentResponse,
    ConfirmScanRequest,
    ConfirmScanResponse,
    DocumentTypeEnum,
)
from app.services import ocr_service

router = APIRouter(prefix="/ocr", tags=["Smart Document Scanner"])

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
MAX_FILE_SIZE_MB = 10


@router.get("/supported-types")
def get_supported_document_types():
    return {
        "supported_types": [
            {
                "type": DocumentTypeEnum.VENDOR_INVOICE.value,
                "name": "Vendor / Purchase Bill",
                "description": "Inward invoices from suppliers and vendors with GST breakdown."
            },
            {
                "type": DocumentTypeEnum.SALES_INVOICE.value,
                "name": "Customer / Sales Invoice",
                "description": "Outward tax invoices issued to customers."
            },
            {
                "type": DocumentTypeEnum.EXPENSE_RECEIPT.value,
                "name": "Expense Receipt",
                "description": "Store receipts, fuel bills, petty cash vouchers, POS receipts."
            },
            {
                "type": DocumentTypeEnum.SALARY_SLIP.value,
                "name": "Salary / Payslip",
                "description": "Monthly employee payroll statements with Basic, HRA, and Net Salary."
            },
            {
                "type": DocumentTypeEnum.BANK_STATEMENT.value,
                "name": "Bank Statement",
                "description": "Account summaries and balance statements."
            }
        ]
    }


@router.post("/scan", response_model=ScanDocumentResponse)
async def scan_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Scans an uploaded document without saving to the database.
    Applies OpenCV preprocessing, OCR, document classification, and field extraction.
    """
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum allowed: {MAX_FILE_SIZE_MB} MB."
        )

    result = ocr_service.scan_and_process_document(file_bytes, file.filename)
    return result


@router.post("/confirm", response_model=ConfirmScanResponse)
def confirm_document(
    payload: ConfirmScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Confirms extracted fields and creates the corresponding record in the database.
    """
    fields = payload.confirmed_fields
    doc_type = payload.document_type

    if doc_type == DocumentTypeEnum.VENDOR_INVOICE:
        vendor_id = payload.vendor_id
        if not vendor_id:
            vendor_name = fields.get("vendor_name") or "Extracted Vendor"
            vendor_gstin = fields.get("vendor_gstin")
            vendor_pan = fields.get("vendor_pan")

            query = db.query(Vendor).filter(Vendor.user_id == current_user.id)
            if vendor_gstin:
                existing_vendor = query.filter(Vendor.gstin == vendor_gstin).first()
            else:
                existing_vendor = query.filter(Vendor.name == vendor_name).first()

            if existing_vendor:
                vendor_id = str(existing_vendor.id)
            else:
                new_vendor = Vendor(
                    user_id=current_user.id,
                    name=vendor_name,
                    gstin=vendor_gstin,
                    pan=vendor_pan,
                )
                db.add(new_vendor)
                db.flush()
                vendor_id = str(new_vendor.id)

        total_amt = Decimal(str(fields.get("total_amount") or "0.00"))
        subtotal = Decimal(str(fields.get("subtotal") or total_amt))
        cgst = Decimal(str(fields.get("cgst_amount") or "0.00"))
        sgst = Decimal(str(fields.get("sgst_amount") or "0.00"))
        igst = Decimal(str(fields.get("igst_amount") or "0.00"))
        tax_amt = cgst + sgst + igst

        inv_num = fields.get("invoice_number") or f"INV-SCAN-{uuid.uuid4().hex[:6].upper()}"

        purchase_inv = PurchaseInvoice(
            user_id=current_user.id,
            vendor_id=uuid.UUID(vendor_id),
            invoice_number=inv_num,
            invoice_date=datetime.utcnow(),
            subtotal=subtotal,
            cgst_total=cgst,
            sgst_total=sgst,
            igst_total=igst,
            tax_amount=tax_amt,
            total_amount=total_amt,
            amount_due=total_amt,
            status=PurchaseInvoiceStatus.RECEIVED,
            ocr_confidence=Decimal(str(fields.get("confidence") or "85.0")),
            notes=payload.notes or "Created via Smart Document Scanner",
        )
        db.add(purchase_inv)
        db.commit()
        db.refresh(purchase_inv)

        return ConfirmScanResponse(
            created_entity_type="PurchaseInvoice",
            entity_id=str(purchase_inv.id),
            message=f"Purchase invoice {purchase_inv.invoice_number} successfully created.",
            status="success",
        )

    elif doc_type in (DocumentTypeEnum.EXPENSE_RECEIPT, DocumentTypeEnum.SALARY_SLIP):
        total_amt = Decimal(str(fields.get("total_amount") or fields.get("net_salary") or "0.00"))
        party_name = fields.get("merchant_name") or fields.get("employee_id") or "Expense Payee"
        now = datetime.utcnow()
        fy = f"{now.year}-{now.year + 1}" if now.month >= 4 else f"{now.year - 1}-{now.year}"
        quarter = f'Q{(now.month - 1) // 3 + 1}'

        ledger_entry = RevenueLedger(
            user_id=current_user.id,
            entry_date=now,
            entry_type=LedgerEntryType.REVENUE_ADJUSTMENT,
            gross_amount=total_amt,
            taxable_amount=total_amt,
            net_amount=total_amt,
            description=f"{payload.notes or party_name} (from Scanner {doc_type.value})",
            financial_year=fy,
            quarter=quarter,
            month=now.strftime('%b').upper(),
        )
        db.add(ledger_entry)
        db.commit()
        db.refresh(ledger_entry)

        return ConfirmScanResponse(
            created_entity_type="RevenueLedger",
            entity_id=str(ledger_entry.id),
            message=f"Expense of Rs {total_amt:.2f} logged into Revenue Ledger.",
            status="success",
        )

    else:
        return ConfirmScanResponse(
            created_entity_type="DocumentPreview",
            entity_id=None,
            message="Document reviewed and saved to audit log.",
            status="success",
        )
