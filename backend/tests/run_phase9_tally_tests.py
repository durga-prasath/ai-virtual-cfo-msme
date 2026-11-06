# backend/tests/run_phase9_tally_tests.py
"""
PHASE 9 TEST SUITE - Tally XML Sync Engine
"""
import sys
import random
import string
from decimal import Decimal
import xml.etree.ElementTree as ET

sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from main import app
from app.db.database import SessionLocal
from app.models.sales_invoice import SalesInvoice, InvoiceStatus
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.payment import Payment, PaymentDirection, PaymentStatus, PaymentMethod
from app.services.tally_xml_service import (
    export_sales_invoices_to_tally_xml,
    export_purchase_invoices_to_tally_xml,
    export_payments_to_tally_xml,
    get_tally_export_summary,
)

client = TestClient(app, raise_server_exceptions=True)
context = {}
results = []


def run(name, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
        results.append((name, True, None))
    except AssertionError as e:
        print(f"  [FAIL] {name}: {e}")
        results.append((name, False, str(e)))
    except Exception as e:
        print(f"  [FAIL] {name}: UNEXPECTED {type(e).__name__}: {e}")
        results.append((name, False, str(e)))


def rand_gstin():
    state = random.randint(10, 35)
    letters = ''.join(random.choices(string.ascii_uppercase, k=5))
    digits = ''.join(random.choices(string.digits, k=4))
    alpha = random.choice(string.ascii_uppercase)
    pos = random.choice('123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    chk = random.choice(string.digits + string.ascii_uppercase)
    return f"{state:02d}{letters}{digits}{alpha}{pos}Z{chk}"


def rand_email():
    return f"tally_user_{random.randint(10000,99999)}@cfodemo.com"


# ─────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────

def t01_auth_setup_and_seed_data():
    email = rand_email()
    pwd = "TestPass@123"
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Tally Sync User",
        "email": email,
        "password": pwd,
        "business_name": "Tally Traders Ltd",
        "gstin": rand_gstin(),
    })
    assert r.status_code in (200, 201)
    user_id = r.json().get("id") or r.json().get("user_id")
    context["user_id"] = user_id

    r_login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    token = r_login.json()["access_token"]
    context["headers"] = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    try:
        import uuid
        uid = uuid.UUID(user_id)
        cust = Customer(user_id=uid, name="Tally Customer Pvt Ltd")
        vend = Vendor(user_id=uid, name="Tally Supplier Corp")
        db.add_all([cust, vend])
        db.flush()

        # Sales Invoice
        sales_inv = SalesInvoice(
            user_id=uid,
            customer_id=cust.id,
            invoice_number="INV-TALLY-001",
            subtotal=Decimal("10000.00"),
            cgst_total=Decimal("900.00"),
            sgst_total=Decimal("900.00"),
            tax_amount=Decimal("1800.00"),
            total_amount=Decimal("11800.00"),
            status=InvoiceStatus.SENT,
        )
        # Purchase Invoice
        purch_inv = PurchaseInvoice(
            user_id=uid,
            vendor_id=vend.id,
            invoice_number="BILL-TALLY-101",
            subtotal=Decimal("8000.00"),
            cgst_total=Decimal("720.00"),
            sgst_total=Decimal("720.00"),
            tax_amount=Decimal("1440.00"),
            total_amount=Decimal("9440.00"),
            status=PurchaseInvoiceStatus.APPROVED,
        )
        db.add_all([sales_inv, purch_inv])
        db.flush()

        # Receipt Payment
        pay = Payment(
            user_id=uid,
            sales_invoice_id=sales_inv.id,
            customer_id=cust.id,
            direction=PaymentDirection.INCOMING,
            amount=Decimal("11800.00"),
            status=PaymentStatus.COMPLETED,
            payment_method=PaymentMethod.BANK_TRANSFER,
            transaction_reference=f"TALLY-TXN-{random.randint(10000, 99999)}",
        )
        db.add(pay)
        db.commit()
    finally:
        db.close()


def t02_sales_invoices_xml_structure():
    import uuid
    db = SessionLocal()
    try:
        xml_str = export_sales_invoices_to_tally_xml(db, uuid.UUID(context["user_id"]))
        root = ET.fromstring(xml_str)
        assert root.tag == "ENVELOPE"
        header = root.find("HEADER")
        assert header is not None
        assert header.find("TALLYREQUEST").text == "Import Data"
        voucher = root.find(".//VOUCHER")
        assert voucher is not None
        assert voucher.attrib["VCHTYPE"] == "Sales"
        assert voucher.find("VOUCHERNUMBER").text == "INV-TALLY-001"
        assert len(voucher.find("DATE").text) == 8  # YYYYMMDD
    finally:
        db.close()


def t03_purchase_invoices_xml_structure():
    import uuid
    db = SessionLocal()
    try:
        xml_str = export_purchase_invoices_to_tally_xml(db, uuid.UUID(context["user_id"]))
        root = ET.fromstring(xml_str)
        voucher = root.find(".//VOUCHER")
        assert voucher is not None
        assert voucher.attrib["VCHTYPE"] == "Purchase"
        assert voucher.find("VOUCHERNUMBER").text == "BILL-TALLY-101"
        ledgers = voucher.findall("ALLLEDGERENTRIES.LIST")
        assert len(ledgers) >= 2
    finally:
        db.close()


def t04_payments_xml_structure():
    import uuid
    db = SessionLocal()
    try:
        xml_str = export_payments_to_tally_xml(db, uuid.UUID(context["user_id"]))
        root = ET.fromstring(xml_str)
        voucher = root.find(".//VOUCHER")
        assert voucher is not None
        assert voucher.attrib["VCHTYPE"] == "Receipt"
        ledgers = voucher.findall("ALLLEDGERENTRIES.LIST")
        assert len(ledgers) == 2
        names = [l.find("LEDGERNAME").text for l in ledgers]
        assert "Bank Account" in names
        assert "Tally Customer Pvt Ltd" in names
    finally:
        db.close()


def t05_api_tally_summary():
    r = client.get("/api/v1/erp/tally/summary", headers=context["headers"])
    assert r.status_code == 200
    data = r.json()
    assert data["exportable_sales_invoices"] >= 1
    assert data["exportable_purchase_invoices"] >= 1
    assert data["exportable_receipt_payments"] >= 1
    assert data["format"] == "TallyXML"


def t06_api_export_invoices_xml():
    r = client.get("/api/v1/erp/tally/export/invoices", headers=context["headers"])
    assert r.status_code == 200
    assert "application/xml" in r.headers["content-type"]
    assert "<ENVELOPE>" in r.text
    assert "INV-TALLY-001" in r.text


def t07_api_export_purchases_xml():
    r = client.get("/api/v1/erp/tally/export/purchases", headers=context["headers"])
    assert r.status_code == 200
    assert "application/xml" in r.headers["content-type"]
    assert "<ENVELOPE>" in r.text
    assert "BILL-TALLY-101" in r.text


def t08_api_export_payments_xml():
    r = client.get("/api/v1/erp/tally/export/payments", headers=context["headers"])
    assert r.status_code == 200
    assert "application/xml" in r.headers["content-type"]
    assert "<ENVELOPE>" in r.text
    assert "Receipt" in r.text


if __name__ == "__main__":
    print("=" * 65)
    print("  PHASE 9 TEST SUITE - TALLY XML SYNC ENGINE")
    print("=" * 65)
    tests = [
        ("T01  Auth Setup & Database Seeding",       t01_auth_setup_and_seed_data),
        ("T02  Sales Invoices TallyXML Structure",   t02_sales_invoices_xml_structure),
        ("T03  Purchase Invoices TallyXML Structure",t03_purchase_invoices_xml_structure),
        ("T04  Payment Receipts TallyXML Structure", t04_payments_xml_structure),
        ("T05  API: GET /erp/tally/summary",         t05_api_tally_summary),
        ("T06  API: GET /erp/tally/export/invoices", t06_api_export_invoices_xml),
        ("T07  API: GET /erp/tally/export/purchases",t07_api_export_purchases_xml),
        ("T08  API: GET /erp/tally/export/payments", t08_api_export_payments_xml),
    ]
    for name, fn in tests:
        run(name, fn)
    print("-" * 65)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  Results: {passed} passed  |  {failed} failed  |  {len(results)} total")
    print("-" * 65)
    if failed == 0:
        print("  ALL 8 PHASE 9 TESTS PASSED!")
    sys.exit(0 if failed == 0 else 1)
