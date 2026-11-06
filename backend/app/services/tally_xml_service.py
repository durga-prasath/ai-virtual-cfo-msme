# backend/app/services/tally_xml_service.py

"""
PHASE 9: TALLY XML SYNC ENGINE (TALLY PRIME XML IMPORT FORMAT)

Standard TallyXML Envelope Structure:
<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <DATA>
            <TALLYMESSAGE xmlns:UDF="TallyUDF">
                ... Vouchers ...
            </TALLYMESSAGE>
        </DATA>
    </BODY>
</ENVELOPE>

Rules for Tally Compliance:
1. Dates: Strictly YYYYMMDD (e.g. 20260912).
2. Amounts: Positive 2-decimal string f"{abs(amount):.2f}".
3. ISDEEMEDPOSITIVE: "Yes" for Debit entries, "No" for Credit entries.
4. Ledger Names:
   - Sales: Customer Name (Debtor), Sales Account, CGST, SGST, IGST.
   - Purchases: Vendor Name (Creditor), Purchase Account, Input CGST, Input SGST, Input IGST.
   - Receipts: Bank/Cash (Debtor), Customer Name (Creditor).
5. REMOTEID: Document UUID to prevent duplicate imports into Tally.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
import xml.etree.ElementTree as ET
from xml.dom import minidom

from sqlalchemy.orm import Session

from app.models.sales_invoice import SalesInvoice, InvoiceStatus
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.payment import Payment, PaymentDirection, PaymentStatus


def _format_date(dt: Optional[datetime]) -> str:
    """Returns date in YYYYMMDD format."""
    if not dt:
        dt = datetime.utcnow()
    return dt.strftime("%Y%m%d")


def _format_amt(amount: Optional[Decimal]) -> str:
    """Returns absolute 2-decimal string."""
    if amount is None:
        amount = Decimal("0.00")
    return f"{abs(Decimal(str(amount))):.2f}"


def _prettify(elem: ET.Element) -> str:
    """Returns formatted XML string with xml declaration."""
    rough_string = ET.tostring(elem, "utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _create_envelope() -> tuple[ET.Element, ET.Element]:
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    tally_req = ET.SubElement(header, "TALLYREQUEST")
    tally_req.text = "Import Data"

    body = ET.SubElement(envelope, "BODY")
    data = ET.SubElement(body, "DATA")
    return envelope, data


# ─────────────────────────────────────────────
# 1. SALES INVOICES XML
# ─────────────────────────────────────────────

def export_sales_invoices_to_tally_xml(db: Session, user_id: UUID) -> str:
    """
    Exports all active sales invoices (SENT, PAID, OVERDUE) into Tally XML format.
    """
    invoices = db.query(SalesInvoice).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE])
    ).all()

    envelope, data = _create_envelope()
    tally_msg = ET.SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})

    for inv in invoices:
        voucher = ET.SubElement(tally_msg, "VOUCHER", {
            "REMOTEID": str(inv.id),
            "VCHTYPE": "Sales",
            "ACTION": "Create"
        })
        
        ET.SubElement(voucher, "DATE").text = _format_date(inv.invoice_date)
        ET.SubElement(voucher, "NARRATION").text = f"Sales Invoice #{inv.invoice_number}"
        ET.SubElement(voucher, "VOUCHERTYPENAME").text = "Sales"
        ET.SubElement(voucher, "VOUCHERNUMBER").text = inv.invoice_number
        customer_name = inv.customer.name if inv.customer else "Sundry Debtors"
        ET.SubElement(voucher, "PARTYLEDGERNAME").text = customer_name

        # Party Ledger Entry (Debit - Total Amount)
        all_ledger_party = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(all_ledger_party, "LEDGERNAME").text = customer_name
        ET.SubElement(all_ledger_party, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(all_ledger_party, "AMOUNT").text = f"-{_format_amt(inv.total_amount)}"

        # Sales Account Entry (Credit - Subtotal)
        all_ledger_sales = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(all_ledger_sales, "LEDGERNAME").text = "Sales Account"
        ET.SubElement(all_ledger_sales, "ISDEEMEDPOSITIVE").text = "No"
        ET.SubElement(all_ledger_sales, "AMOUNT").text = _format_amt(inv.subtotal)

        # Tax Ledgers (Credit)
        cgst = Decimal(str(inv.cgst_total or 0))
        sgst = Decimal(str(inv.sgst_total or 0))
        igst = Decimal(str(inv.igst_total or 0))

        if cgst > 0:
            cgst_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(cgst_el, "LEDGERNAME").text = "Output CGST"
            ET.SubElement(cgst_el, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(cgst_el, "AMOUNT").text = _format_amt(cgst)

        if sgst > 0:
            sgst_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(sgst_el, "LEDGERNAME").text = "Output SGST"
            ET.SubElement(sgst_el, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(sgst_el, "AMOUNT").text = _format_amt(sgst)

        if igst > 0:
            igst_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(igst_el, "LEDGERNAME").text = "Output IGST"
            ET.SubElement(igst_el, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(igst_el, "AMOUNT").text = _format_amt(igst)

    return _prettify(envelope)


# ─────────────────────────────────────────────
# 2. PURCHASE INVOICES XML
# ─────────────────────────────────────────────

def export_purchase_invoices_to_tally_xml(db: Session, user_id: UUID) -> str:
    """
    Exports all approved or received purchase invoices into Tally XML format.
    """
    invoices = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.user_id == user_id,
        PurchaseInvoice.status.in_([PurchaseInvoiceStatus.RECEIVED, PurchaseInvoiceStatus.APPROVED, PurchaseInvoiceStatus.PAID])
    ).all()

    envelope, data = _create_envelope()
    tally_msg = ET.SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})

    for inv in invoices:
        voucher = ET.SubElement(tally_msg, "VOUCHER", {
            "REMOTEID": str(inv.id),
            "VCHTYPE": "Purchase",
            "ACTION": "Create"
        })

        ET.SubElement(voucher, "DATE").text = _format_date(inv.invoice_date)
        ET.SubElement(voucher, "NARRATION").text = f"Purchase Bill #{inv.invoice_number}"
        ET.SubElement(voucher, "VOUCHERTYPENAME").text = "Purchase"
        ET.SubElement(voucher, "VOUCHERNUMBER").text = inv.invoice_number
        vendor_name = inv.vendor.name if inv.vendor else "Sundry Creditors"
        ET.SubElement(voucher, "PARTYLEDGERNAME").text = vendor_name

        # Party Ledger Entry (Credit - Total Amount)
        all_ledger_party = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(all_ledger_party, "LEDGERNAME").text = vendor_name
        ET.SubElement(all_ledger_party, "ISDEEMEDPOSITIVE").text = "No"
        ET.SubElement(all_ledger_party, "AMOUNT").text = _format_amt(inv.total_amount)

        # Purchase Account Entry (Debit - Subtotal)
        all_ledger_purch = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(all_ledger_purch, "LEDGERNAME").text = "Purchase Account"
        ET.SubElement(all_ledger_purch, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(all_ledger_purch, "AMOUNT").text = f"-{_format_amt(inv.subtotal)}"

        # Input Tax Ledgers (Debit)
        cgst = Decimal(str(inv.cgst_total or 0))
        sgst = Decimal(str(inv.sgst_total or 0))
        igst = Decimal(str(inv.igst_total or 0))

        if cgst > 0:
            cgst_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(cgst_el, "LEDGERNAME").text = "Input CGST"
            ET.SubElement(cgst_el, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(cgst_el, "AMOUNT").text = f"-{_format_amt(cgst)}"

        if sgst > 0:
            sgst_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(sgst_el, "LEDGERNAME").text = "Input SGST"
            ET.SubElement(sgst_el, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(sgst_el, "AMOUNT").text = f"-{_format_amt(sgst)}"

        if igst > 0:
            igst_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(igst_el, "LEDGERNAME").text = "Input IGST"
            ET.SubElement(igst_el, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(igst_el, "AMOUNT").text = f"-{_format_amt(igst)}"

    return _prettify(envelope)


# ─────────────────────────────────────────────
# 3. RECEIPT PAYMENTS XML
# ─────────────────────────────────────────────

def export_payments_to_tally_xml(db: Session, user_id: UUID) -> str:
    """
    Exports customer payment receipts into Tally XML format (Receipt vouchers).
    """
    payments = db.query(Payment).filter(
        Payment.user_id == user_id,
        Payment.direction == PaymentDirection.INCOMING,
        Payment.status == PaymentStatus.COMPLETED
    ).all()

    envelope, data = _create_envelope()
    tally_msg = ET.SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})

    for p in payments:
        voucher = ET.SubElement(tally_msg, "VOUCHER", {
            "REMOTEID": str(p.id),
            "VCHTYPE": "Receipt",
            "ACTION": "Create"
        })

        ET.SubElement(voucher, "DATE").text = _format_date(p.payment_date)
        ref = p.transaction_reference or str(p.id)[:8]
        ET.SubElement(voucher, "NARRATION").text = f"Payment Receipt ref #{ref}"
        ET.SubElement(voucher, "VOUCHERTYPENAME").text = "Receipt"
        ET.SubElement(voucher, "VOUCHERNUMBER").text = ref

        customer_name = p.customer.name if p.customer else "Sundry Debtors"
        ET.SubElement(voucher, "PARTYLEDGERNAME").text = customer_name

        # Customer Account (Credit)
        cust_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(cust_el, "LEDGERNAME").text = customer_name
        ET.SubElement(cust_el, "ISDEEMEDPOSITIVE").text = "No"
        ET.SubElement(cust_el, "AMOUNT").text = _format_amt(p.amount)

        # Bank/Cash Account (Debit)
        bank_ledger = "Bank Account" if p.payment_method and p.payment_method.value != "cash" else "Cash"
        bank_el = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(bank_el, "LEDGERNAME").text = bank_ledger
        ET.SubElement(bank_el, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(bank_el, "AMOUNT").text = f"-{_format_amt(p.amount)}"

    return _prettify(envelope)


def get_tally_export_summary(db: Session, user_id: UUID) -> dict:
    sales_cnt = db.query(SalesInvoice).filter(
        SalesInvoice.user_id == user_id,
        SalesInvoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PAID, InvoiceStatus.OVERDUE])
    ).count()

    purch_cnt = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.user_id == user_id,
        PurchaseInvoice.status.in_([PurchaseInvoiceStatus.RECEIVED, PurchaseInvoiceStatus.APPROVED, PurchaseInvoiceStatus.PAID])
    ).count()

    pay_cnt = db.query(Payment).filter(
        Payment.user_id == user_id,
        Payment.direction == PaymentDirection.INCOMING,
        Payment.status == PaymentStatus.COMPLETED
    ).count()

    return {
        "exportable_sales_invoices": sales_cnt,
        "exportable_purchase_invoices": purch_cnt,
        "exportable_receipt_payments": pay_cnt,
        "tally_version_supported": "Tally Prime & Tally.ERP 9",
        "format": "TallyXML",
    }
