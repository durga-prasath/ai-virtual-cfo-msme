# backend/app/schemas/gst_schema.py

from pydantic import BaseModel, Field, field_validator, ConfigDict
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum
import re

from app.models.gst_record import ReturnType, FilingStatus


# ─────────────────────────────────────────────
# VALIDATION HELPERS
# ─────────────────────────────────────────────

def validate_period_format(v: str) -> str:
    v = v.strip()
    if not re.match(r'^(0[1-9]|1[0-2])-[0-9]{4}$', v):
        raise ValueError("Invalid return period format. Expected 'MM-YYYY' (e.g. '04-2026')")
    return v


# ─────────────────────────────────────────────
# GSTR-1 SCHEMAS
# ─────────────────────────────────────────────

class GSTR1ItemBreakup(BaseModel):
    gst_rate: Decimal = Field(..., description="GST rate slab e.g. 18.00")
    taxable_value: Decimal = Field(..., description="Taxable value")
    cgst: Decimal = Field(default=Decimal('0.00'))
    sgst: Decimal = Field(default=Decimal('0.00'))
    igst: Decimal = Field(default=Decimal('0.00'))
    cess: Decimal = Field(default=Decimal('0.00'))


class GSTR1B2BInvoice(BaseModel):
    customer_name: str
    customer_gstin: str
    invoice_number: str
    invoice_date: datetime
    total_amount: Decimal
    place_of_supply: str
    reverse_charge: str = "N"
    invoice_type: str = "Regular"
    items: List[GSTR1ItemBreakup] = []


class GSTR1B2CLInvoice(BaseModel):
    customer_name: str
    invoice_number: str
    invoice_date: datetime
    total_amount: Decimal
    place_of_supply: str
    items: List[GSTR1ItemBreakup] = []


class GSTR1B2CSSummary(BaseModel):
    place_of_supply: str
    gst_rate: Decimal
    taxable_value: Decimal
    igst: Decimal = Decimal('0.00')
    cgst: Decimal = Decimal('0.00')
    sgst: Decimal = Decimal('0.00')
    cess: Decimal = Decimal('0.00')


class GSTR1HSNSummary(BaseModel):
    hsn_code: str
    description: Optional[str] = None
    uqc: str = "PCS"
    total_quantity: Decimal
    total_value: Decimal
    taxable_value: Decimal
    igst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    cess_amount: Decimal = Decimal('0.00')


class GSTR1DocSummary(BaseModel):
    nature_of_document: str = "Invoices for outward supply"
    from_serial_number: Optional[str] = None
    to_serial_number: Optional[str] = None
    total_number: int = 0
    cancelled_number: int = 0
    net_issued_number: int = 0


class GSTR1ReportResponse(BaseModel):
    return_period: str
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    due_date: datetime
    status: str
    
    # Financial Aggregates
    total_invoices: int
    total_taxable_value: Decimal
    total_cgst: Decimal
    total_sgst: Decimal
    total_igst: Decimal
    total_cess: Decimal = Decimal('0.00')
    total_tax: Decimal
    total_invoice_value: Decimal

    # Detailed tables
    b2b_invoices: List[GSTR1B2BInvoice] = []
    b2cl_invoices: List[GSTR1B2CLInvoice] = []
    b2cs_summaries: List[GSTR1B2CSSummary] = []
    hsn_summary: List[GSTR1HSNSummary] = []
    doc_summary: GSTR1DocSummary


# ─────────────────────────────────────────────
# GSTR-3B SCHEMAS
# ─────────────────────────────────────────────

class Table31OutwardSupplies(BaseModel):
    taxable_value: Decimal = Decimal('0.00')
    igst: Decimal = Decimal('0.00')
    cgst: Decimal = Decimal('0.00')
    sgst: Decimal = Decimal('0.00')
    cess: Decimal = Decimal('0.00')
    total_tax: Decimal = Decimal('0.00')


class Table32InterStateSupplies(BaseModel):
    place_of_supply: str
    taxable_value: Decimal = Decimal('0.00')
    igst: Decimal = Decimal('0.00')


class Table4EligibleITC(BaseModel):
    itc_igst: Decimal = Decimal('0.00')
    itc_cgst: Decimal = Decimal('0.00')
    itc_sgst: Decimal = Decimal('0.00')
    itc_cess: Decimal = Decimal('0.00')
    total_itc: Decimal = Decimal('0.00')


class Table51LateFeeInterest(BaseModel):
    is_overdue: bool = False
    days_overdue: int = 0
    interest: Decimal = Decimal('0.00')
    late_fee: Decimal = Decimal('0.00')
    total_interest_late_fee: Decimal = Decimal('0.00')


class Table61TaxPayable(BaseModel):
    tax_liability_igst: Decimal = Decimal('0.00')
    tax_liability_cgst: Decimal = Decimal('0.00')
    tax_liability_sgst: Decimal = Decimal('0.00')
    tax_liability_cess: Decimal = Decimal('0.00')
    total_tax_liability: Decimal = Decimal('0.00')

    itc_utilized_igst: Decimal = Decimal('0.00')
    itc_utilized_cgst: Decimal = Decimal('0.00')
    itc_utilized_sgst: Decimal = Decimal('0.00')
    itc_utilized_cess: Decimal = Decimal('0.00')
    total_itc_utilized: Decimal = Decimal('0.00')

    net_tax_payable_igst: Decimal = Decimal('0.00')
    net_tax_payable_cgst: Decimal = Decimal('0.00')
    net_tax_payable_sgst: Decimal = Decimal('0.00')
    net_tax_payable_cess: Decimal = Decimal('0.00')
    total_net_tax_payable: Decimal = Decimal('0.00')


class GSTR3BReportResponse(BaseModel):
    return_period: str
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    due_date: datetime
    status: str
    table_3_1_outward_supplies: Table31OutwardSupplies
    table_3_2_inter_state_supplies: List[Table32InterStateSupplies] = []
    table_4_eligible_itc: Table4EligibleITC
    table_5_1_late_fee_interest: Table51LateFeeInterest
    table_6_1_payment_of_tax: Table61TaxPayable


# ─────────────────────────────────────────────
# RECONCILIATION & TAX LIABILITY SCHEMAS
# ─────────────────────────────────────────────

class GSTReconciliationResponse(BaseModel):
    return_period: str
    gstr1_taxable_value: Decimal
    gstr3b_taxable_value: Decimal
    taxable_variance: Decimal

    gstr1_total_tax: Decimal
    gstr3b_outward_tax: Decimal
    tax_variance: Decimal

    total_purchase_itc: Decimal
    claimed_itc: Decimal
    itc_variance: Decimal

    reconciliation_status: str
    variance_amount: Decimal
    discrepancies: List[str] = []


class TaxLiabilitySummaryResponse(BaseModel):
    return_period: str
    due_date: datetime
    is_overdue: bool
    filing_status: str

    gross_output_tax: Decimal
    total_itc_available: Decimal
    net_tax_payable: Decimal
    interest_late_fee: Decimal
    total_payable_amount: Decimal

    breakup: Dict[str, Dict[str, Decimal]]


# ─────────────────────────────────────────────
# FILING & RECORD SCHEMAS
# ─────────────────────────────────────────────

class GSTFileReturnRequest(BaseModel):
    return_type: ReturnType
    return_period: str
    acknowledgement_number: Optional[str] = Field(None, max_length=20)
    tax_paid: Optional[Decimal] = Field(Decimal('0.00'), ge=0)

    @field_validator('return_period')
    @classmethod
    def validate_period(cls, v):
        return validate_period_format(v)


class GSTRecordResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    return_type: ReturnType
    return_period: str
    due_date: datetime
    filed_date: Optional[datetime] = None
    acknowledgement_number: Optional[str] = None
    status: FilingStatus
    auto_file_enabled: bool
    total_taxable_value: Decimal
    total_tax: Decimal
    total_itc: Decimal
    tax_payable: Decimal
    tax_paid: Decimal
    interest_late_fee: Decimal
    reconciliation_status: Optional[str] = None
    variance_amount: Decimal
    created_at: datetime
    updated_at: Optional[datetime] = None
