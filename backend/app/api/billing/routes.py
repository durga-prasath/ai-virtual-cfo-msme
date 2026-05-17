# backend/app/api/billing/routes.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
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
def create_customer_endpoint(
    payload: CustomerCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ← Protected
):
    """Create a customer. User ID is taken from JWT token — not from request body."""
    # Override whatever user_id the client sent — always use the authenticated user
    payload.user_id = current_user.id
    try:
        return create_customer(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customers", response_model=list[CustomerResponseSchema])
def list_customers_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ← Protected
):
    """List only THIS user's customers. No user_id query param needed."""
    return list_customers(db, user_id=current_user.id, skip=skip, limit=limit)


@router.get("/customers/{customer_id}", response_model=CustomerResponseSchema)
def get_customer_endpoint(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ← Protected
):
    customer = get_customer(db, customer_id, current_user.id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


# ── Products ───────────────────────────────────

@router.post("/products", response_model=ProductResponseSchema, status_code=201)
def create_product_endpoint(
    payload: ProductCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ← Protected
):
    payload.user_id = current_user.id
    try:
        return create_product(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products", response_model=list[ProductResponseSchema])
def list_products_endpoint(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ← Protected
):
    return list_products(db, user_id=current_user.id, skip=skip, limit=limit)


# ── Invoices ───────────────────────────────────

@router.post("/invoices", response_model=InvoiceResponseSchema, status_code=201)
def create_invoice_endpoint(
    payload: InvoiceCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ← Protected
):
    payload.user_id = current_user.id
    try:
        return create_invoice(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponseSchema)
def get_invoice_endpoint(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ← Protected
):
    invoice = get_invoice(db, invoice_id, current_user.id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice