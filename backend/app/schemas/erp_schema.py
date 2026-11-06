# backend/app/schemas/erp_schema.py

"""
Pydantic v2 schemas for ERP Integration (Phase 8).

Covers:
  - Business profile (ERP config, GSTIN, MSME details)
  - ERP sync request/response (Tally, Zoho Books)
  - ERP sync log entry
  - Revenue Ledger entries + P&L report
  - Trial Balance snapshot
"""

from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime
from enum import Enum


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class ERPProviderEnum(str, Enum):
    TALLY   = "tally"
    ZOHO    = "zoho"
    BUSY    = "busy"
    MARG    = "marg"
    INTERNAL = "internal"   # No external ERP — ledger only


class SyncDirectionEnum(str, Enum):
    PUSH = "push"   # Platform → ERP
    PULL = "pull"   # ERP → Platform


class SyncStatusEnum(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    SUCCESS  = "success"
    PARTIAL  = "partial"
    FAILED   = "failed"


class SyncEntityEnum(str, Enum):
    INVOICES  = "invoices"
    PAYMENTS  = "payments"
    VENDORS   = "vendors"
    CUSTOMERS = "customers"
    PRODUCTS  = "products"
    LEDGER    = "ledger"
    ALL       = "all"


class LedgerEntryTypeEnum(str, Enum):
    INVOICE_RAISED      = "invoice_raised"
    PAYMENT_RECEIVED    = "payment_received"
    CREDIT_NOTE         = "credit_note"
    DEBIT_NOTE          = "debit_note"
    REVENUE_ADJUSTMENT  = "revenue_adjustment"
    BAD_DEBT_WRITE_OFF  = "bad_debt_write_off"


# ─────────────────────────────────────────────
# BUSINESS PROFILE
# ─────────────────────────────────────────────

class BusinessProfileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    business_name: str
    legal_name: Optional[str] = None
    business_type: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    cin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: str
    udyam_number: Optional[str] = None
    msme_registered: bool
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_id: Optional[str] = None
    erp_enabled: bool
    erp_provider: Optional[str] = None
    erp_last_sync: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class BusinessProfileUpdateSchema(BaseModel):
    """Partial update — all fields optional."""
    business_name: Optional[str] = None
    legal_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    cin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    udyam_number: Optional[str] = None
    msme_registered: Optional[bool] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_id: Optional[str] = None
    erp_enabled: Optional[bool] = None
    erp_provider: Optional[ERPProviderEnum] = None


# ─────────────────────────────────────────────
# ERP SYNC
# ─────────────────────────────────────────────

class ERPSyncRequestSchema(BaseModel):
    """Trigger a sync run."""
    provider: ERPProviderEnum = ERPProviderEnum.TALLY
    direction: SyncDirectionEnum = SyncDirectionEnum.PUSH
    entities: List[SyncEntityEnum] = Field(
        default=[SyncEntityEnum.ALL],
        description="Which data types to sync"
    )
    from_date: Optional[str] = Field(
        None,
        description="ISO date — sync records created/updated from this date (YYYY-MM-DD)"
    )
    dry_run: bool = Field(
        False,
        description="If true, calculate what would be synced without actually doing it"
    )


class ERPSyncEntityResultSchema(BaseModel):
    """Per-entity sync outcome."""
    entity: str
    total: int        # Total records to sync
    synced: int       # Successfully synced
    skipped: int      # Already up to date
    failed: int       # Errors
    errors: List[str] = []


class ERPSyncResultSchema(BaseModel):
    """Full sync run result."""
    sync_id: UUID
    provider: str
    direction: str
    status: SyncStatusEnum
    dry_run: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    entities: List[ERPSyncEntityResultSchema]
    total_synced: int
    total_failed: int
    message: str


class ERPSyncLogSchema(BaseModel):
    """Historical sync log entry."""
    sync_id: UUID
    provider: str
    direction: str
    status: str
    total_synced: int
    total_failed: int
    started_at: datetime
    completed_at: Optional[datetime] = None


class ERPConfigSchema(BaseModel):
    """ERP connectivity status."""
    erp_enabled: bool
    erp_provider: Optional[str]
    erp_last_sync: Optional[datetime]
    connection_status: str       # connected, not_configured, error
    pending_sync_count: int      # records not yet synced


# ─────────────────────────────────────────────
# REVENUE LEDGER
# ─────────────────────────────────────────────

class RevenueLedgerEntrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    invoice_id: Optional[UUID] = None
    payment_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None

    entry_date: datetime
    entry_type: str
    reference_number: Optional[str] = None
    description: Optional[str] = None

    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    total_tax: Decimal
    net_amount: Decimal

    financial_year: str
    quarter: str
    month: Optional[str] = None

    synced_to_erp: bool
    erp_sync_date: Optional[datetime] = None
    erp_reference: Optional[str] = None

    created_at: datetime


class RevenueLedgerCreateSchema(BaseModel):
    """Manual ledger adjustment entry (adjustments, bad-debt write-offs etc.)."""
    entry_type: LedgerEntryTypeEnum
    entry_date: datetime
    description: str
    gross_amount: Decimal = Field(..., ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    cgst_amount: Decimal = Field(default=Decimal("0"), ge=0)
    sgst_amount: Decimal = Field(default=Decimal("0"), ge=0)
    igst_amount: Decimal = Field(default=Decimal("0"), ge=0)
    reference_number: Optional[str] = None
    invoice_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None


# ─────────────────────────────────────────────
# P&L / TRIAL BALANCE
# ─────────────────────────────────────────────

class PLLineItem(BaseModel):
    label: str
    amount: Decimal


class ProfitLossReportSchema(BaseModel):
    """
    Simplified P&L for the requested period.
    Revenue − Cost of Revenue = Gross Profit
    Gross Profit − Operating Expenses = Net Profit
    """
    period_label: str           # e.g. "FY 2024-25" or "Apr 2025"
    from_date: str
    to_date: str
    generated_at: datetime

    # Revenue
    gross_invoiced: Decimal
    total_discount: Decimal
    net_revenue: Decimal        # gross_invoiced - discount

    # Tax collected (liability, not income)
    total_tax_collected: Decimal
    cgst_collected: Decimal
    sgst_collected: Decimal
    igst_collected: Decimal

    # Receipts
    total_collected: Decimal    # actual payments received

    # Payables (purchase invoices approved)
    total_purchases: Decimal
    total_purchase_tax_paid: Decimal

    # Gross profit (simplified)
    gross_profit: Decimal       # net_revenue - total_purchases
    gross_profit_margin: float  # %

    # Bad debts
    bad_debts_written_off: Decimal

    # Net position
    net_profit: Decimal
    net_profit_margin: float

    # Breakdown by month
    monthly_breakdown: List[Dict] = []


class TrialBalanceSchema(BaseModel):
    """
    Simplified trial balance: debits vs credits across ledger entry types.
    """
    as_of: datetime
    financial_year: str

    total_debits: Decimal
    total_credits: Decimal
    balance: Decimal            # credits - debits (should be 0 for balanced books)

    entries_by_type: List[Dict]  # [{entry_type, debit, credit, net}]
    is_balanced: bool
