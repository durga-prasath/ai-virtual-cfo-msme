# backend/app/services/gst_service.py

"""
GST REPORTING & COMPLIANCE SERVICE LAYER

Handles:
1. GSTR-1 generation (B2B, B2C Large, B2C Small, HSN summary, Document summary)
2. GSTR-3B generation (Tables 3.1, 3.2, 4.0 ITC, 5.1 Late fees, 6.1 Payment of tax)
3. GST Reconciliation (GSTR-1 vs GSTR-3B variance audit and purchase ITC matching)
4. Live Tax Liability calculation for Virtual CFO executive dashboards
5. GST Portal offline tool compliant JSON payload generation
6. Filing lifecycle management (PENDING -> READY_TO_FILE -> FILED)
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
from datetime import datetime, date
from calendar import monthrange
from typing import Optional, List, Dict, Any, Tuple
import logging
import json
import re

from fastapi import HTTPException, status

from app.models.gst_record import GSTRecord, ReturnType, FilingStatus
from app.models.sales_invoice import SalesInvoice, InvoiceStatus
from app.models.sales_invoice_item import SalesInvoiceItem
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.customer import Customer
from app.models.product import Product
from app.models.user import User
from app.models.business import Business
from app.schemas.gst_schema import (
    GSTR1ReportResponse,
    GSTR1B2BInvoice,
    GSTR1B2CLInvoice,
    GSTR1B2CSSummary,
    GSTR1HSNSummary,
    GSTR1DocSummary,
    GSTR1ItemBreakup,
    GSTR3BReportResponse,
    Table31OutwardSupplies,
    Table32InterStateSupplies,
    Table4EligibleITC,
    Table51LateFeeInterest,
    Table61TaxPayable,
    GSTReconciliationResponse,
    TaxLiabilitySummaryResponse,
    GSTFileReturnRequest,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# STATE CODE LOOKUP (INDIAN GST STANDARD)
# ─────────────────────────────────────────────

GST_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh (New)",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}


# ─────────────────────────────────────────────
# PRECISION & DATE HELPERS
# ─────────────────────────────────────────────

def round_decimal(value: Decimal, places: int = 2) -> Decimal:
    if value is None:
        return Decimal('0.00')
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def parse_period(return_period: str) -> Tuple[datetime, datetime]:
    """
    Parses 'MM-YYYY' into start datetime (1st of month 00:00:00)
    and end datetime (last of month 23:59:59).
    """
    try:
        parts = return_period.strip().split("-")
        month = int(parts[0])
        year = int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError()
        _, last_day = monthrange(year, month)
        start_dt = datetime(year, month, 1, 0, 0, 0)
        end_dt = datetime(year, month, last_day, 23, 59, 59, 999999)
        return start_dt, end_dt
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid return period: '{return_period}'. Must be 'MM-YYYY' e.g. '04-2026'."
        )


def get_statutory_due_date(return_type: ReturnType, return_period: str) -> datetime:
    """
    Returns statutory filing deadline:
    GSTR-1: 11th of succeeding month
    GSTR-3B: 20th of succeeding month
    """
    parts = return_period.strip().split("-")
    month = int(parts[0])
    year = int(parts[1])

    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year

    day = 11 if return_type == ReturnType.GSTR1 else 20
    return datetime(next_year, next_month, day, 23, 59, 59)


def get_place_of_supply(customer: Optional[Customer], default_state: Optional[str] = "Tamil Nadu") -> str:
    if customer:
        if customer.gstin and len(customer.gstin) >= 2:
            code = customer.gstin[:2]
            if code in GST_STATE_CODES:
                return f"{code}-{GST_STATE_CODES[code]}"
        if customer.state:
            return customer.state
    return default_state or "33-Tamil Nadu"


def get_user_business_details(db: Session, user_id: UUID) -> Tuple[Optional[str], Optional[str]]:
    business = db.query(Business).filter(Business.user_id == user_id).first()
    if business:
        return business.business_name, business.gstin
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        return user.business_name, user.gstin
    return None, None


# ─────────────────────────────────────────────
# 1. GSTR-1 REPORT GENERATION
# ─────────────────────────────────────────────

def generate_gstr1(db: Session, user_id: UUID, return_period: str) -> GSTR1ReportResponse:
    """
    Generates GSTR-1 outward supplies return:
    - B2B Invoices (registered customers with GSTIN)
    - B2C Large (inter-state, invoice > ₹2.5L, unregistered)
    - B2C Small (all other unregistered supplies grouped by POS and rate)
    - HSN/SAC summary
    - Document issued summary
    """
    start_dt, end_dt = parse_period(return_period)
    due_date = get_statutory_due_date(ReturnType.GSTR1, return_period)
    business_name, user_gstin = get_user_business_details(db, user_id)

    # Valid outward invoices: SENT, PAID, OVERDUE (exclude CANCELLED and DRAFT)
    invoices = db.query(SalesInvoice).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.invoice_date >= start_dt,
        SalesInvoice.invoice_date <= end_dt,
        SalesInvoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE])
    ).order_by(SalesInvoice.invoice_date.asc()).all()

    # Cancelled invoices count in the period for Doc Summary
    cancelled_count = db.query(func.count(SalesInvoice.id)).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.invoice_date >= start_dt,
        SalesInvoice.invoice_date <= end_dt,
        SalesInvoice.status == InvoiceStatus.CANCELLED
    ).scalar() or 0

    total_invoices = len(invoices)
    total_taxable = Decimal('0.00')
    total_cgst = Decimal('0.00')
    total_sgst = Decimal('0.00')
    total_igst = Decimal('0.00')
    total_cess = Decimal('0.00')
    total_tax = Decimal('0.00')
    total_invoice_value = Decimal('0.00')

    b2b_invoices: List[GSTR1B2BInvoice] = []
    b2cl_invoices: List[GSTR1B2CLInvoice] = []
    b2cs_groups: Dict[Tuple[str, Decimal], Dict[str, Decimal]] = {}
    hsn_groups: Dict[str, Dict[str, Any]] = {}

    invoice_numbers: List[str] = []

    for inv in invoices:
        inv_subtotal = round_decimal(Decimal(str(inv.subtotal)))
        inv_tax = round_decimal(Decimal(str(inv.tax_amount)))
        inv_cgst = round_decimal(Decimal(str(inv.cgst_total)))
        inv_sgst = round_decimal(Decimal(str(inv.sgst_total)))
        inv_igst = round_decimal(Decimal(str(inv.igst_total)))
        inv_total = round_decimal(Decimal(str(inv.total_amount)))

        total_taxable += inv_subtotal
        total_cgst += inv_cgst
        total_sgst += inv_sgst
        total_igst += inv_igst
        total_tax += inv_tax
        total_invoice_value += inv_total

        invoice_numbers.append(inv.invoice_number)

        customer = inv.customer
        pos = get_place_of_supply(customer)
        has_gstin = bool(customer and customer.gstin and len(customer.gstin.strip()) == 15)

        # Build item breakups for this invoice
        item_breakups: List[GSTR1ItemBreakup] = []
        for item in inv.items:
            item_taxable = round_decimal(Decimal(str(item.unit_price)) * Decimal(str(item.quantity)))
            item_breakups.append(GSTR1ItemBreakup(
                gst_rate=round_decimal(Decimal(str(item.gst_rate))),
                taxable_value=item_taxable,
                cgst=round_decimal(Decimal(str(item.cgst_amount))),
                sgst=round_decimal(Decimal(str(item.sgst_amount))),
                igst=round_decimal(Decimal(str(item.igst_amount))),
                cess=Decimal('0.00')
            ))

            # Aggregate for HSN summary
            hsn_code = (item.product.hsn_code if item.product and item.product.hsn_code else "UNKNOWN").strip()
            desc = item.product.name if item.product else item.description
            unit = item.product.unit if (item.product and item.product.unit) else "PCS"
            qty = Decimal(str(item.quantity))
            line_tot = round_decimal(Decimal(str(item.total)))

            if hsn_code not in hsn_groups:
                hsn_groups[hsn_code] = {
                    "hsn_code": hsn_code,
                    "description": desc,
                    "uqc": unit,
                    "total_quantity": Decimal('0.000'),
                    "total_value": Decimal('0.00'),
                    "taxable_value": Decimal('0.00'),
                    "igst_amount": Decimal('0.00'),
                    "cgst_amount": Decimal('0.00'),
                    "sgst_amount": Decimal('0.00'),
                    "cess_amount": Decimal('0.00'),
                }
            hsn_groups[hsn_code]["total_quantity"] += qty
            hsn_groups[hsn_code]["total_value"] += line_tot
            hsn_groups[hsn_code]["taxable_value"] += item_taxable
            hsn_groups[hsn_code]["igst_amount"] += round_decimal(Decimal(str(item.igst_amount)))
            hsn_groups[hsn_code]["cgst_amount"] += round_decimal(Decimal(str(item.cgst_amount)))
            hsn_groups[hsn_code]["sgst_amount"] += round_decimal(Decimal(str(item.sgst_amount)))

        # Categorize invoice: B2B vs B2C Large vs B2C Small
        if has_gstin:
            b2b_invoices.append(GSTR1B2BInvoice(
                customer_name=customer.name if customer else "Registered Customer",
                customer_gstin=customer.gstin.strip(),
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date,
                total_amount=inv_total,
                place_of_supply=pos,
                reverse_charge="N",
                invoice_type="Regular",
                items=item_breakups
            ))
        elif inv_igst > Decimal('0.00') and inv_total > Decimal('250000.00'):
            # B2C Large: Inter-state unregistered and > ₹2.5 Lakhs
            b2cl_invoices.append(GSTR1B2CLInvoice(
                customer_name=customer.name if customer else "Unregistered Consumer",
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date,
                total_amount=inv_total,
                place_of_supply=pos,
                items=item_breakups
            ))
        else:
            # B2C Small: Grouped by POS and GST Rate
            for itm in item_breakups:
                key = (pos, itm.gst_rate)
                if key not in b2cs_groups:
                    b2cs_groups[key] = {
                        "taxable_value": Decimal('0.00'),
                        "igst": Decimal('0.00'),
                        "cgst": Decimal('0.00'),
                        "sgst": Decimal('0.00'),
                        "cess": Decimal('0.00')
                    }
                b2cs_groups[key]["taxable_value"] += itm.taxable_value
                b2cs_groups[key]["igst"] += itm.igst
                b2cs_groups[key]["cgst"] += itm.cgst
                b2cs_groups[key]["sgst"] += itm.sgst

    # Format B2CS summaries
    b2cs_summaries: List[GSTR1B2CSSummary] = [
        GSTR1B2CSSummary(
            place_of_supply=k[0],
            gst_rate=k[1],
            taxable_value=round_decimal(v["taxable_value"]),
            igst=round_decimal(v["igst"]),
            cgst=round_decimal(v["cgst"]),
            sgst=round_decimal(v["sgst"]),
            cess=round_decimal(v["cess"])
        )
        for k, v in b2cs_groups.items()
    ]

    # Format HSN summaries
    hsn_summary: List[GSTR1HSNSummary] = [
        GSTR1HSNSummary(
            hsn_code=v["hsn_code"],
            description=v["description"],
            uqc=v["uqc"],
            total_quantity=round_decimal(v["total_quantity"], places=3),
            total_value=round_decimal(v["total_value"]),
            taxable_value=round_decimal(v["taxable_value"]),
            igst_amount=round_decimal(v["igst_amount"]),
            cgst_amount=round_decimal(v["cgst_amount"]),
            sgst_amount=round_decimal(v["sgst_amount"]),
            cess_amount=round_decimal(v["cess_amount"])
        )
        for v in hsn_groups.values()
    ]

    # Format Document summary
    from_serial = invoice_numbers[0] if invoice_numbers else None
    to_serial = invoice_numbers[-1] if invoice_numbers else None
    doc_summary = GSTR1DocSummary(
        from_serial_number=from_serial,
        to_serial_number=to_serial,
        total_number=total_invoices + cancelled_count,
        cancelled_number=cancelled_count,
        net_issued_number=total_invoices
    )

    # Build Government Portal compliant JSON payload
    portal_json = build_gstr1_portal_json(
        user_gstin=user_gstin,
        return_period=return_period,
        b2b_invoices=b2b_invoices,
        b2cl_invoices=b2cl_invoices,
        b2cs_summaries=b2cs_summaries,
        hsn_summary=hsn_summary,
        doc_summary=doc_summary
    )

    # Save or update GSTRecord
    save_or_update_gst_record(
        db=db,
        user_id=user_id,
        return_type=ReturnType.GSTR1,
        return_period=return_period,
        due_date=due_date,
        taxable_value=total_taxable,
        cgst=total_cgst,
        sgst=total_sgst,
        igst=total_igst,
        cess=total_cess,
        total_tax=total_tax,
        itc_cgst=Decimal('0.00'),
        itc_sgst=Decimal('0.00'),
        itc_igst=Decimal('0.00'),
        itc_cess=Decimal('0.00'),
        total_itc=Decimal('0.00'),
        tax_payable=total_tax,
        json_payload=json.dumps(portal_json)
    )

    return GSTR1ReportResponse(
        return_period=return_period,
        business_name=business_name,
        gstin=user_gstin,
        due_date=due_date,
        status="ready_to_file" if total_invoices > 0 else "pending",
        total_invoices=total_invoices,
        total_taxable_value=round_decimal(total_taxable),
        total_cgst=round_decimal(total_cgst),
        total_sgst=round_decimal(total_sgst),
        total_igst=round_decimal(total_igst),
        total_cess=round_decimal(total_cess),
        total_tax=round_decimal(total_tax),
        total_invoice_value=round_decimal(total_invoice_value),
        b2b_invoices=b2b_invoices,
        b2cl_invoices=b2cl_invoices,
        b2cs_summaries=b2cs_summaries,
        hsn_summary=hsn_summary,
        doc_summary=doc_summary
    )


# ─────────────────────────────────────────────
# 2. GSTR-3B REPORT GENERATION
# ─────────────────────────────────────────────

def generate_gstr3b(db: Session, user_id: UUID, return_period: str) -> GSTR3BReportResponse:
    """
    Generates GSTR-3B monthly return:
    - Table 3.1: Details of Outward Supplies and inward supplies liable to reverse charge
    - Table 3.2: Inter-state supplies to unregistered persons
    - Table 4.0: Eligible Input Tax Credit (ITC) from purchase invoices
    - Table 5.1: Estimated Interest & Late fee if past due date
    - Table 6.1: Payment of Tax (Net tax payable after ITC offset)
    """
    start_dt, end_dt = parse_period(return_period)
    due_date = get_statutory_due_date(ReturnType.GSTR3B, return_period)
    business_name, user_gstin = get_user_business_details(db, user_id)

    # 1. Outward supplies from SalesInvoices
    sales_invoices = db.query(SalesInvoice).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.invoice_date >= start_dt,
        SalesInvoice.invoice_date <= end_dt,
        SalesInvoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE])
    ).all()

    taxable_val = Decimal('0.00')
    out_igst = Decimal('0.00')
    out_cgst = Decimal('0.00')
    out_sgst = Decimal('0.00')
    out_cess = Decimal('0.00')

    interstate_unreg: Dict[str, Dict[str, Decimal]] = {}

    for inv in sales_invoices:
        inv_sub = round_decimal(Decimal(str(inv.subtotal)))
        inv_igst = round_decimal(Decimal(str(inv.igst_total)))
        inv_cgst = round_decimal(Decimal(str(inv.cgst_total)))
        inv_sgst = round_decimal(Decimal(str(inv.sgst_total)))

        taxable_val += inv_sub
        out_igst += inv_igst
        out_cgst += inv_cgst
        out_sgst += inv_sgst

        # Table 3.2: Inter-state unregistered supplies
        customer = inv.customer
        has_gstin = bool(customer and customer.gstin and len(customer.gstin.strip()) == 15)
        if not has_gstin and inv_igst > Decimal('0.00'):
            pos = get_place_of_supply(customer)
            if pos not in interstate_unreg:
                interstate_unreg[pos] = {"taxable_value": Decimal('0.00'), "igst": Decimal('0.00')}
            interstate_unreg[pos]["taxable_value"] += inv_sub
            interstate_unreg[pos]["igst"] += inv_igst

    total_out_tax = out_igst + out_cgst + out_sgst + out_cess

    table_3_1 = Table31OutwardSupplies(
        taxable_value=round_decimal(taxable_val),
        igst=round_decimal(out_igst),
        cgst=round_decimal(out_cgst),
        sgst=round_decimal(out_sgst),
        cess=round_decimal(out_cess),
        total_tax=round_decimal(total_out_tax)
    )

    table_3_2 = [
        Table32InterStateSupplies(
            place_of_supply=pos,
            taxable_value=round_decimal(data["taxable_value"]),
            igst=round_decimal(data["igst"])
        )
        for pos, data in interstate_unreg.items()
    ]

    # 2. Inward supplies (Eligible ITC) from PurchaseInvoices
    purchase_invoices = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.user_id == user_id,
        PurchaseInvoice.invoice_date >= start_dt,
        PurchaseInvoice.invoice_date <= end_dt,
        PurchaseInvoice.status.in_([
            PurchaseInvoiceStatus.RECEIVED,
            PurchaseInvoiceStatus.APPROVED,
            PurchaseInvoiceStatus.PAID
        ])
    ).all()

    itc_igst = Decimal('0.00')
    itc_cgst = Decimal('0.00')
    itc_sgst = Decimal('0.00')
    itc_cess = Decimal('0.00')

    for pinv in purchase_invoices:
        itc_igst += round_decimal(Decimal(str(pinv.igst_total or 0)))
        itc_cgst += round_decimal(Decimal(str(pinv.cgst_total or 0)))
        itc_sgst += round_decimal(Decimal(str(pinv.sgst_total or 0)))

    total_itc = itc_igst + itc_cgst + itc_sgst + itc_cess

    table_4 = Table4EligibleITC(
        itc_igst=round_decimal(itc_igst),
        itc_cgst=round_decimal(itc_cgst),
        itc_sgst=round_decimal(itc_sgst),
        itc_cess=round_decimal(itc_cess),
        total_itc=round_decimal(total_itc)
    )

    # 3. Table 6.1 Tax Payable & ITC Utilization
    # Offset rules: IGST ITC -> IGST, CGST, SGST; CGST ITC -> CGST; SGST ITC -> SGST
    util_igst = min(out_igst, itc_igst)
    rem_out_igst = out_igst - util_igst
    rem_itc_igst = itc_igst - util_igst

    util_cgst = min(out_cgst, itc_cgst)
    rem_out_cgst = out_cgst - util_cgst
    if rem_out_cgst > Decimal('0.00') and rem_itc_igst > Decimal('0.00'):
        extra_cgst_util = min(rem_out_cgst, rem_itc_igst)
        util_cgst += extra_cgst_util
        rem_out_cgst -= extra_cgst_util
        rem_itc_igst -= extra_cgst_util

    util_sgst = min(out_sgst, itc_sgst)
    rem_out_sgst = out_sgst - util_sgst
    if rem_out_sgst > Decimal('0.00') and rem_itc_igst > Decimal('0.00'):
        extra_sgst_util = min(rem_out_sgst, rem_itc_igst)
        util_sgst += extra_sgst_util
        rem_out_sgst -= extra_sgst_util
        rem_itc_igst -= extra_sgst_util

    net_payable_igst = rem_out_igst
    net_payable_cgst = rem_out_cgst
    net_payable_sgst = rem_out_sgst
    net_payable_cess = out_cess
    total_net_payable = net_payable_igst + net_payable_cgst + net_payable_sgst + net_payable_cess
    total_itc_utilized = util_igst + util_cgst + util_sgst

    table_6_1 = Table61TaxPayable(
        tax_liability_igst=round_decimal(out_igst),
        tax_liability_cgst=round_decimal(out_cgst),
        tax_liability_sgst=round_decimal(out_sgst),
        tax_liability_cess=round_decimal(out_cess),
        total_tax_liability=round_decimal(total_out_tax),
        itc_utilized_igst=round_decimal(util_igst),
        itc_utilized_cgst=round_decimal(util_cgst),
        itc_utilized_sgst=round_decimal(util_sgst),
        itc_utilized_cess=Decimal('0.00'),
        total_itc_utilized=round_decimal(total_itc_utilized),
        net_tax_payable_igst=round_decimal(net_payable_igst),
        net_tax_payable_cgst=round_decimal(net_payable_cgst),
        net_tax_payable_sgst=round_decimal(net_payable_sgst),
        net_tax_payable_cess=round_decimal(net_payable_cess),
        total_net_tax_payable=round_decimal(total_net_payable)
    )

    # 4. Table 5.1 Late fee and Interest estimation
    now = datetime.utcnow()
    is_overdue = now > due_date
    days_overdue = (now - due_date).days if is_overdue else 0

    if is_overdue and days_overdue > 0:
        # ₹50/day standard (₹25 CGST + ₹25 SGST) or ₹20 if nil return, capped at ₹5000
        daily_fee = Decimal('20.00') if total_out_tax == Decimal('0.00') else Decimal('50.00')
        est_late_fee = min(daily_fee * Decimal(str(days_overdue)), Decimal('5000.00'))
        # 18% per annum interest on net tax payable
        est_interest = round_decimal((total_net_payable * Decimal('0.18') / Decimal('365')) * Decimal(str(days_overdue)))
    else:
        est_late_fee = Decimal('0.00')
        est_interest = Decimal('0.00')

    table_5_1 = Table51LateFeeInterest(
        is_overdue=is_overdue,
        days_overdue=days_overdue,
        interest=est_interest,
        late_fee=est_late_fee,
        total_interest_late_fee=round_decimal(est_interest + est_late_fee)
    )

    # Build Government Portal compliant JSON payload
    portal_json = build_gstr3b_portal_json(
        user_gstin=user_gstin,
        return_period=return_period,
        table_3_1=table_3_1,
        table_3_2=table_3_2,
        table_4=table_4,
        table_5_1=table_5_1,
        table_6_1=table_6_1
    )

    # Save or update GSTRecord
    save_or_update_gst_record(
        db=db,
        user_id=user_id,
        return_type=ReturnType.GSTR3B,
        return_period=return_period,
        due_date=due_date,
        taxable_value=taxable_val,
        cgst=out_cgst,
        sgst=out_sgst,
        igst=out_igst,
        cess=out_cess,
        total_tax=total_out_tax,
        itc_cgst=itc_cgst,
        itc_sgst=itc_sgst,
        itc_igst=itc_igst,
        itc_cess=itc_cess,
        total_itc=total_itc,
        tax_payable=total_net_payable,
        interest_late_fee=est_interest + est_late_fee,
        json_payload=json.dumps(portal_json)
    )

    return GSTR3BReportResponse(
        return_period=return_period,
        business_name=business_name,
        gstin=user_gstin,
        due_date=due_date,
        status="ready_to_file" if (len(sales_invoices) > 0 or len(purchase_invoices) > 0) else "pending",
        table_3_1_outward_supplies=table_3_1,
        table_3_2_inter_state_supplies=table_3_2,
        table_4_eligible_itc=table_4,
        table_5_1_late_fee_interest=table_5_1,
        table_6_1_payment_of_tax=table_6_1
    )


# ─────────────────────────────────────────────
# 3. GST RECONCILIATION & VARIANCE AUDIT
# ─────────────────────────────────────────────

def reconcile_gst(db: Session, user_id: UUID, return_period: str) -> GSTReconciliationResponse:
    """
    Performs multi-point reconciliation:
    1. GSTR-1 Outward Supplies vs GSTR-3B Outward Supplies
    2. Recorded Purchase Invoices vs Claimed ITC
    3. Structural audits (missing HSN codes, unregistered parties with suspicious tax slabs)
    """
    gstr1 = generate_gstr1(db, user_id, return_period)
    gstr3b = generate_gstr3b(db, user_id, return_period)

    taxable_var = round_decimal(abs(gstr1.total_taxable_value - gstr3b.table_3_1_outward_supplies.taxable_value))
    tax_var = round_decimal(abs(gstr1.total_tax - gstr3b.table_3_1_outward_supplies.total_tax))

    total_purchase_itc = gstr3b.table_4_eligible_itc.total_itc
    claimed_itc = gstr3b.table_6_1_payment_of_tax.total_itc_utilized
    itc_var = round_decimal(abs(total_purchase_itc - claimed_itc))

    discrepancies: List[str] = []

    if taxable_var > Decimal('0.00'):
        discrepancies.append(
            f"Taxable value variance of ₹{taxable_var} between GSTR-1 (₹{gstr1.total_taxable_value}) "
            f"and GSTR-3B (₹{gstr3b.table_3_1_outward_supplies.taxable_value})"
        )

    if tax_var > Decimal('0.00'):
        discrepancies.append(
            f"Tax liability variance of ₹{tax_var} between GSTR-1 (₹{gstr1.total_tax}) "
            f"and GSTR-3B (₹{gstr3b.table_3_1_outward_supplies.total_tax})"
        )

    # Check for missing HSN codes in GSTR-1
    for hsn_item in gstr1.hsn_summary:
        if hsn_item.hsn_code == "UNKNOWN":
            discrepancies.append(
                f"Products with missing HSN/SAC code detected (Total Taxable Value: ₹{hsn_item.taxable_value})"
            )

    # Check for draft or unfinalized invoices within the period
    start_dt, end_dt = parse_period(return_period)
    draft_count = db.query(func.count(SalesInvoice.id)).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.invoice_date >= start_dt,
        SalesInvoice.invoice_date <= end_dt,
        SalesInvoice.status == InvoiceStatus.DRAFT
    ).scalar() or 0

    if draft_count > 0:
        discrepancies.append(
            f"{draft_count} invoice(s) are still in DRAFT status and were omitted from GST returns. Send them to include."
        )

    total_variance = taxable_var + tax_var
    reconciliation_status = "reconciled" if len(discrepancies) == 0 else "variance_detected"

    # Update reconciliation fields on GSTRecord for this period
    for rtype in [ReturnType.GSTR1, ReturnType.GSTR3B]:
        record = db.query(GSTRecord).filter(
            GSTRecord.user_id == user_id,
            GSTRecord.return_type == rtype,
            GSTRecord.return_period == return_period
        ).first()
        if record:
            record.reconciliation_status = reconciliation_status
            record.variance_amount = total_variance

    db.commit()

    return GSTReconciliationResponse(
        return_period=return_period,
        gstr1_taxable_value=gstr1.total_taxable_value,
        gstr3b_taxable_value=gstr3b.table_3_1_outward_supplies.taxable_value,
        taxable_variance=taxable_var,
        gstr1_total_tax=gstr1.total_tax,
        gstr3b_outward_tax=gstr3b.table_3_1_outward_supplies.total_tax,
        tax_variance=tax_var,
        total_purchase_itc=total_purchase_itc,
        claimed_itc=claimed_itc,
        itc_variance=itc_var,
        reconciliation_status=reconciliation_status,
        variance_amount=total_variance,
        discrepancies=discrepancies
    )


# ─────────────────────────────────────────────
# 4. REAL-TIME TAX LIABILITY SUMMARY
# ─────────────────────────────────────────────

def get_tax_liability(db: Session, user_id: UUID, return_period: str) -> TaxLiabilitySummaryResponse:
    """
    Computes live GST position for current period.
    Directly feeds the Virtual CFO Dashboard 'GST Payable' KPI card.
    """
    gstr3b = generate_gstr3b(db, user_id, return_period)

    t3 = gstr3b.table_3_1_outward_supplies
    t4 = gstr3b.table_4_eligible_itc
    t6 = gstr3b.table_6_1_payment_of_tax
    t5 = gstr3b.table_5_1_late_fee_interest

    total_due = t6.total_net_tax_payable + t5.total_interest_late_fee

    # Fetch filing status from record if exists
    rec = db.query(GSTRecord).filter(
        GSTRecord.user_id == user_id,
        GSTRecord.return_type == ReturnType.GSTR3B,
        GSTRecord.return_period == return_period
    ).first()

    status_str = rec.status.value if rec else "pending"

    return TaxLiabilitySummaryResponse(
        return_period=return_period,
        due_date=gstr3b.due_date,
        is_overdue=t5.is_overdue,
        filing_status=status_str,
        gross_output_tax=t3.total_tax,
        total_itc_available=t4.total_itc,
        net_tax_payable=t6.total_net_tax_payable,
        interest_late_fee=t5.total_interest_late_fee,
        total_payable_amount=round_decimal(total_due),
        breakup={
            "output_tax": {
                "igst": t3.igst,
                "cgst": t3.cgst,
                "sgst": t3.sgst,
                "total": t3.total_tax
            },
            "itc": {
                "igst": t4.itc_igst,
                "cgst": t4.itc_cgst,
                "sgst": t4.itc_sgst,
                "total": t4.total_itc
            },
            "net_payable": {
                "igst": t6.net_tax_payable_igst,
                "cgst": t6.net_tax_payable_cgst,
                "sgst": t6.net_tax_payable_sgst,
                "total": t6.total_net_tax_payable
            }
        }
    )


# ─────────────────────────────────────────────
# 5. FILING LIFECYCLE & HISTORICAL RECORDS
# ─────────────────────────────────────────────

def file_return(db: Session, user_id: UUID, payload: GSTFileReturnRequest) -> GSTRecord:
    """
    Transitions GST return status from READY_TO_FILE/PENDING to FILED.
    Records statutory acknowledgement number and settled tax amount.
    """
    record = db.query(GSTRecord).filter(
        GSTRecord.user_id == user_id,
        GSTRecord.return_type == payload.return_type,
        GSTRecord.return_period == payload.return_period
    ).first()

    if not record:
        # Pre-generate to create record
        if payload.return_type == ReturnType.GSTR1:
            generate_gstr1(db, user_id, payload.return_period)
        else:
            generate_gstr3b(db, user_id, payload.return_period)

        record = db.query(GSTRecord).filter(
            GSTRecord.user_id == user_id,
            GSTRecord.return_type == payload.return_type,
            GSTRecord.return_period == payload.return_period
        ).first()

    if record.status == FilingStatus.FILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{payload.return_type.value.upper()} for period {payload.return_period} is already FILED."
        )

    record.status = FilingStatus.FILED
    record.filed_date = datetime.utcnow()
    record.acknowledgement_number = payload.acknowledgement_number
    if payload.tax_paid is not None:
        record.tax_paid = round_decimal(payload.tax_paid)

    db.commit()
    db.refresh(record)
    logger.info(f"{payload.return_type.value.upper()} for {payload.return_period} marked as FILED by user {user_id}")
    return record


def list_gst_records(db: Session, user_id: UUID, return_period: Optional[str] = None) -> List[GSTRecord]:
    query = db.query(GSTRecord).filter(GSTRecord.user_id == user_id)
    if return_period:
        query = query.filter(GSTRecord.return_period == return_period)
    return query.order_by(GSTRecord.due_date.desc()).all()


def get_gst_portal_json(db: Session, user_id: UUID, return_type: ReturnType, return_period: str) -> Dict[str, Any]:
    """
    Retrieves the generated official portal-ready JSON payload for GSTR-1 or GSTR-3B.
    """
    record = db.query(GSTRecord).filter(
        GSTRecord.user_id == user_id,
        GSTRecord.return_type == return_type,
        GSTRecord.return_period == return_period
    ).first()

    if not record or not record.json_payload:
        if return_type == ReturnType.GSTR1:
            generate_gstr1(db, user_id, return_period)
        else:
            generate_gstr3b(db, user_id, return_period)

        record = db.query(GSTRecord).filter(
            GSTRecord.user_id == user_id,
            GSTRecord.return_type == return_type,
            GSTRecord.return_period == return_period
        ).first()

    if not record or not record.json_payload:
        raise HTTPException(status_code=404, detail="JSON payload not found for the requested return period")

    return json.loads(record.json_payload)


# ─────────────────────────────────────────────
# 6. PORTAL JSON PAYLOAD BUILDERS & DB SYNC
# ─────────────────────────────────────────────

def save_or_update_gst_record(
    db: Session,
    user_id: UUID,
    return_type: ReturnType,
    return_period: str,
    due_date: datetime,
    taxable_value: Decimal,
    cgst: Decimal,
    sgst: Decimal,
    igst: Decimal,
    cess: Decimal,
    total_tax: Decimal,
    itc_cgst: Decimal,
    itc_sgst: Decimal,
    itc_igst: Decimal,
    itc_cess: Decimal,
    total_itc: Decimal,
    tax_payable: Decimal,
    json_payload: str,
    interest_late_fee: Decimal = Decimal('0.00')
) -> GSTRecord:
    record = db.query(GSTRecord).filter(
        GSTRecord.user_id == user_id,
        GSTRecord.return_type == return_type,
        GSTRecord.return_period == return_period
    ).first()

    if not record:
        record = GSTRecord(
            id=uuid4(),
            user_id=user_id,
            return_type=return_type,
            return_period=return_period,
            due_date=due_date,
            status=FilingStatus.READY_TO_FILE,
        )
        db.add(record)

    record.total_taxable_value = round_decimal(taxable_value)
    record.total_cgst = round_decimal(cgst)
    record.total_sgst = round_decimal(sgst)
    record.total_igst = round_decimal(igst)
    record.total_cess = round_decimal(cess)
    record.total_tax = round_decimal(total_tax)

    record.itc_cgst = round_decimal(itc_cgst)
    record.itc_sgst = round_decimal(itc_sgst)
    record.itc_igst = round_decimal(itc_igst)
    record.itc_cess = round_decimal(itc_cess)
    record.total_itc = round_decimal(total_itc)

    record.tax_payable = round_decimal(tax_payable)
    record.interest_late_fee = round_decimal(interest_late_fee)
    record.json_payload = json_payload

    if record.status != FilingStatus.FILED:
        record.status = FilingStatus.READY_TO_FILE

    db.commit()
    db.refresh(record)
    return record


def build_gstr1_portal_json(
    user_gstin: Optional[str],
    return_period: str,
    b2b_invoices: List[GSTR1B2BInvoice],
    b2cl_invoices: List[GSTR1B2CLInvoice],
    b2cs_summaries: List[GSTR1B2CSSummary],
    hsn_summary: List[GSTR1HSNSummary],
    doc_summary: GSTR1DocSummary
) -> Dict[str, Any]:
    # Portal format: fp = MMYYYY
    fp = return_period.replace("-", "")

    # Group B2B by recipient GSTIN
    b2b_by_ctin: Dict[str, List[Dict[str, Any]]] = {}
    for inv in b2b_invoices:
        ctin = inv.customer_gstin
        if ctin not in b2b_by_ctin:
            b2b_by_ctin[ctin] = []

        inv_data = {
            "inum": inv.invoice_number,
            "idt": inv.invoice_date.strftime("%d-%m-%Y"),
            "val": float(inv.total_amount),
            "pos": inv.place_of_supply.split("-")[0] if "-" in inv.place_of_supply else inv.place_of_supply,
            "rchrg": inv.reverse_charge,
            "inv_typ": "R",
            "itms": [
                {
                    "num": idx + 1,
                    "itm_det": {
                        "rt": float(itm.gst_rate),
                        "txval": float(itm.taxable_value),
                        "iamt": float(itm.igst),
                        "camt": float(itm.cgst),
                        "samt": float(itm.sgst),
                        "csamt": float(itm.cess)
                    }
                }
                for idx, itm in enumerate(inv.items)
            ]
        }
        b2b_by_ctin[ctin].append(inv_data)

    b2b_payload = [{"ctin": ctin, "inv": invs} for ctin, invs in b2b_by_ctin.items()]

    b2cs_payload = [
        {
            "sply_ty": "INTER" if s.igst > Decimal('0.00') else "INTRA",
            "rt": float(s.gst_rate),
            "typ": "OE",
            "pos": s.place_of_supply.split("-")[0] if "-" in s.place_of_supply else s.place_of_supply,
            "txval": float(s.taxable_value),
            "iamt": float(s.igst),
            "camt": float(s.cgst),
            "samt": float(s.sgst),
            "csamt": float(s.cess)
        }
        for s in b2cs_summaries
    ]

    hsn_payload = [
        {
            "num": idx + 1,
            "hsn_sc": h.hsn_code,
            "desc": h.description or "General",
            "uqc": h.uqc,
            "qty": float(h.total_quantity),
            "val": float(h.total_value),
            "txval": float(h.taxable_value),
            "iamt": float(h.igst_amount),
            "camt": float(h.cgst_amount),
            "samt": float(h.sgst_amount),
            "csamt": float(h.cess_amount)
        }
        for idx, h in enumerate(hsn_summary)
    ]

    return {
        "gstin": user_gstin or "",
        "fp": fp,
        "version": "GSTR1_3.0",
        "hash": "hash_placeholder",
        "b2b": b2b_payload,
        "b2cl": [
            {
                "pos": inv.place_of_supply.split("-")[0] if "-" in inv.place_of_supply else inv.place_of_supply,
                "inv": [
                    {
                        "inum": inv.invoice_number,
                        "idt": inv.invoice_date.strftime("%d-%m-%Y"),
                        "val": float(inv.total_amount),
                        "itms": [
                            {
                                "num": idx + 1,
                                "itm_det": {
                                    "rt": float(itm.gst_rate),
                                    "txval": float(itm.taxable_value),
                                    "iamt": float(itm.igst),
                                    "csamt": float(itm.cess)
                                }
                            }
                            for idx, itm in enumerate(inv.items)
                        ]
                    }
                ]
            }
            for inv in b2cl_invoices
        ],
        "b2cs": b2cs_payload,
        "hsn": {"data": hsn_payload},
        "doc_issue": {
            "doc_det": [
                {
                    "doc_num": 1,
                    "doc_typ": doc_summary.nature_of_document,
                    "docs": [
                        {
                            "num": 1,
                            "from": doc_summary.from_serial_number or "NA",
                            "to": doc_summary.to_serial_number or "NA",
                            "totnum": doc_summary.total_number,
                            "canc": doc_summary.cancelled_number,
                            "net_issue": doc_summary.net_issued_number
                        }
                    ]
                }
            ]
        }
    }


def build_gstr3b_portal_json(
    user_gstin: Optional[str],
    return_period: str,
    table_3_1: Table31OutwardSupplies,
    table_3_2: List[Table32InterStateSupplies],
    table_4: Table4EligibleITC,
    table_5_1: Table51LateFeeInterest,
    table_6_1: Table61TaxPayable
) -> Dict[str, Any]:
    ret_period = return_period.replace("-", "")

    return {
        "gstin": user_gstin or "",
        "ret_period": ret_period,
        "sec_sum": {
            "sup_details": {
                "osup_det": {
                    "txval": float(table_3_1.taxable_value),
                    "iamt": float(table_3_1.igst),
                    "camt": float(table_3_1.cgst),
                    "samt": float(table_3_1.sgst),
                    "csamt": float(table_3_1.cess)
                },
                "isup_rev": {"txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0}
            },
            "inter_sup": {
                "unreg_details": [
                    {
                        "pos": s.place_of_supply.split("-")[0] if "-" in s.place_of_supply else s.place_of_supply,
                        "txval": float(s.taxable_value),
                        "iamt": float(s.igst)
                    }
                    for s in table_3_2
                ]
            },
            "itc_elg": {
                "itc_avl": [
                    {
                        "ty": "OTH",
                        "iamt": float(table_4.itc_igst),
                        "camt": float(table_4.itc_cgst),
                        "samt": float(table_4.itc_sgst),
                        "csamt": float(table_4.itc_cess)
                    }
                ],
                "itc_net": {
                    "iamt": float(table_4.itc_igst),
                    "camt": float(table_4.itc_cgst),
                    "samt": float(table_4.itc_sgst),
                    "csamt": float(table_4.itc_cess)
                }
            },
            "inward_sup": {"isup_details": []},
            "intr_ltfee": {
                "intr_details": {
                    "iamt": float(table_5_1.interest),
                    "camt": 0.0,
                    "samt": 0.0,
                    "csamt": 0.0
                },
                "ltfee_details": {
                    "camt": float(round_decimal(table_5_1.late_fee / Decimal('2'))),
                    "samt": float(round_decimal(table_5_1.late_fee / Decimal('2')))
                }
            },
            "tx_pmt": {
                "tx_py": [
                    {
                        "tran_desc": "Tax payable",
                        "liab_ldg_id": 1,
                        "iamt": float(table_6_1.net_tax_payable_igst),
                        "camt": float(table_6_1.net_tax_payable_cgst),
                        "samt": float(table_6_1.net_tax_payable_sgst),
                        "csamt": float(table_6_1.net_tax_payable_cess)
                    }
                ]
            }
        }
    }
