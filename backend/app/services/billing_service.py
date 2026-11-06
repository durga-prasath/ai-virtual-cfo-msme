# backend/app/services/billing_service.py

from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
import logging
import re

from fastapi import HTTPException, status

from app.models.customer import Customer
from app.models.product import Product
from app.models.sales_invoice import SalesInvoice
from app.models.sales_invoice_item import SalesInvoiceItem
from app.schemas.billing_schema import (
    CustomerCreateSchema,
    ProductCreateSchema,
    InvoiceCreateSchema,
    GSTTypeEnum,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def round_decimal(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def validate_gstin(gstin: str) -> bool:
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
    return bool(re.match(pattern, gstin.upper()))


def generate_invoice_number(db: Session, user_id: UUID) -> str:
    year = datetime.utcnow().year
    count = db.query(func.count(SalesInvoice.id)).filter(
        SalesInvoice.user_id == user_id,
        func.extract('year', SalesInvoice.invoice_date) == year
    ).scalar()
    return f"INV-{year}-{(count or 0) + 1:04d}"


def calculate_gst(subtotal: Decimal, gst_rate: Decimal, gst_type: GSTTypeEnum) -> dict:
    total_gst = round_decimal(subtotal * gst_rate / Decimal('100'))

    if gst_type == GSTTypeEnum.INTRA:
        cgst = round_decimal(total_gst / Decimal('2'))
        sgst = total_gst - cgst
        igst = Decimal('0.00')
    else:
        cgst = Decimal('0.00')
        sgst = Decimal('0.00')
        igst = total_gst

    return {
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "total_gst": total_gst
    }


# ─────────────────────────────────────────────
# CUSTOMER SERVICE
# ─────────────────────────────────────────────

def create_customer(db: Session, data: CustomerCreateSchema) -> Customer:
    if data.gstin and not validate_gstin(data.gstin):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid GSTIN format: {data.gstin}"
        )

    if data.gstin:
        existing = db.query(Customer).filter(
            Customer.gstin == data.gstin,
            Customer.user_id == data.user_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Customer with GSTIN {data.gstin} already exists"
            )

    customer = Customer(
        id=uuid4(),
        user_id=data.user_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        gstin=data.gstin,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
    )
    db.add(customer)
    try:
        db.commit()
        db.refresh(customer)
        return customer
    except Exception as e:
        db.rollback()
        logger.error(f"create_customer failed: {e}")
        raise


def get_customer(db: Session, customer_id: UUID, user_id: UUID) -> Optional[Customer]:
    return db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.user_id == user_id
    ).first()


def list_customers(db: Session, user_id: UUID, skip: int = 0, limit: int = 50):
    return db.query(Customer).filter(
        Customer.user_id == user_id
    ).offset(skip).limit(limit).all()


# ─────────────────────────────────────────────
# PRODUCT SERVICE
# ─────────────────────────────────────────────

def create_product(db: Session, data: ProductCreateSchema) -> Product:
    product = Product(
        id=uuid4(),
        user_id=data.user_id,
        name=data.name,
        description=data.description,
        hsn_code=data.hsn_code,
        base_price=data.base_price,
        gst_rate=data.gst_rate,
        unit=data.unit,
    )
    db.add(product)
    try:
        db.commit()
        db.refresh(product)
        return product
    except Exception as e:
        db.rollback()
        logger.error(f"create_product failed: {e}")
        raise


def list_products(db: Session, user_id: UUID, skip: int = 0, limit: int = 50):
    return db.query(Product).filter(
        Product.user_id == user_id
    ).offset(skip).limit(limit).all()


# ─────────────────────────────────────────────
# INVOICE SERVICE
# ─────────────────────────────────────────────

def create_invoice(db: Session, data: InvoiceCreateSchema) -> SalesInvoice:
    # Validate customer belongs to this user
    customer = db.query(Customer).filter(
        Customer.id == data.customer_id,
        Customer.user_id == data.user_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Process line items
    items_data = []
    inv_subtotal = Decimal('0.00')
    inv_cgst = Decimal('0.00')
    inv_sgst = Decimal('0.00')
    inv_igst = Decimal('0.00')
    inv_tax = Decimal('0.00')

    for item in data.items:
        product = db.query(Product).filter(
            Product.id == item.product_id,
            Product.user_id == data.user_id
        ).first()
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item.product_id} not found"
            )

        line_subtotal = round_decimal(item.quantity * item.unit_price)
        gst = calculate_gst(line_subtotal, product.gst_rate, data.gst_type)
        line_total = round_decimal(line_subtotal + gst["total_gst"])

        inv_subtotal += line_subtotal
        inv_cgst += gst["cgst"]
        inv_sgst += gst["sgst"]
        inv_igst += gst["igst"]
        inv_tax += gst["total_gst"]

        items_data.append({
            "product": product,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "gst_rate": product.gst_rate,
            "cgst_amount": gst["cgst"],
            "sgst_amount": gst["sgst"],
            "igst_amount": gst["igst"],
            "total": line_total,
        })

    inv_subtotal = round_decimal(inv_subtotal)
    inv_tax = round_decimal(inv_tax)
    inv_total = round_decimal(inv_subtotal + inv_tax)

    # Create invoice header
    invoice = SalesInvoice(
        id=uuid4(),
        user_id=data.user_id,
        customer_id=data.customer_id,
        invoice_number=generate_invoice_number(db, data.user_id),
        invoice_date=datetime.utcnow(),
        due_date=data.due_date,
        status="draft",
        subtotal=inv_subtotal,
        tax_amount=inv_tax,
        total_amount=inv_total,
        amount_due=inv_total,
        cgst_total=round_decimal(inv_cgst),
        sgst_total=round_decimal(inv_sgst),
        igst_total=round_decimal(inv_igst),
        notes=data.notes,
    )
    db.add(invoice)
    db.flush()  # Gets invoice.id without committing

    # ── Auto-post to Revenue Ledger ──
    try:
        from app.services.erp_sync_service import post_invoice_to_ledger
        post_invoice_to_ledger(db, invoice)
    except Exception as ledger_err:
        logger.warning(f"Ledger auto-post failed (non-fatal): {ledger_err}")

    # Create line items
    for item_data in items_data:
        line_item = SalesInvoiceItem(
            id=uuid4(),
            invoice_id=invoice.id,
            product_id=item_data["product"].id,
            description=item_data["product"].name,  # ← required field in model
            quantity=item_data["quantity"],
            unit_price=item_data["unit_price"],
            gst_rate=item_data["gst_rate"],
            cgst_amount=item_data["cgst_amount"],
            sgst_amount=item_data["sgst_amount"],
            igst_amount=item_data["igst_amount"],
            total=item_data["total"],
        )
        db.add(line_item)

    try:
        db.commit()
        db.refresh(invoice)
        logger.info(f"Invoice created: {invoice.invoice_number}")
        return invoice
    except Exception as e:
        db.rollback()
        logger.error(f"create_invoice failed: {e}")
        raise


def get_invoice(db: Session, invoice_id: UUID, user_id: UUID) -> Optional[SalesInvoice]:
    return db.query(SalesInvoice).filter(
        SalesInvoice.id == invoice_id,
        SalesInvoice.user_id == user_id
    ).first()