# backend/app/api/billing/routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.database import get_db
from app.schemas.billing_schema import (
    CustomerCreateSchema, CustomerResponseSchema,
    ProductCreateSchema, ProductResponseSchema,
    InvoiceCreateSchema, InvoiceResponseSchema,
)
from app.services.billing_service import (
    create_customer, get_customer, list_customers,
    create_product, list_products,
    create_invoice, get_invoice,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


# ── Customers ──────────────────────────────────

@router.post("/customers", response_model=CustomerResponseSchema, status_code=201)
def create_customer_endpoint(payload: CustomerCreateSchema, db: Session = Depends(get_db)):
    try:
        return create_customer(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customers", response_model=list[CustomerResponseSchema])
def list_customers_endpoint(
    user_id: UUID = Query(...),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    return list_customers(db, user_id=user_id, skip=skip, limit=limit)


@router.get("/customers/{customer_id}", response_model=CustomerResponseSchema)
def get_customer_endpoint(
    customer_id: UUID,
    user_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    customer = get_customer(db, customer_id, user_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


# ── Products ───────────────────────────────────

@router.post("/products", response_model=ProductResponseSchema, status_code=201)
def create_product_endpoint(payload: ProductCreateSchema, db: Session = Depends(get_db)):
    try:
        return create_product(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products", response_model=list[ProductResponseSchema])
def list_products_endpoint(
    user_id: UUID = Query(...),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    return list_products(db, user_id=user_id, skip=skip, limit=limit)


# ── Invoices ───────────────────────────────────

@router.post("/invoices", response_model=InvoiceResponseSchema, status_code=201)
def create_invoice_endpoint(payload: InvoiceCreateSchema, db: Session = Depends(get_db)):
    try:
        return create_invoice(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponseSchema)
def get_invoice_endpoint(
    invoice_id: UUID,
    user_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    invoice = get_invoice(db, invoice_id, user_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice