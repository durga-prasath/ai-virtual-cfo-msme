# backend/tests/run_phase7_chatbot_tests.py
"""
PHASE 7 TEST SUITE - AI Virtual CFO Chatbot & Structured Tool Calling
"""
import sys
import random
import string
from decimal import Decimal

sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from main import app
from app.db.database import SessionLocal
from app.models.sales_invoice import SalesInvoice, InvoiceStatus
from app.models.customer import Customer
from app.models.payment import Payment, PaymentDirection, PaymentStatus, PaymentMethod
from app.services.chatbot_service import (
    get_revenue_summary,
    get_gst_summary,
    get_outstanding_invoices,
    get_customer_summary,
    get_payment_history,
    get_invoice_stats,
    ask_cfo_chatbot,
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
    return f"cfo_user_{random.randint(10000,99999)}@cfodemo.com"


# ─────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────

def t01_auth_setup_and_seed_data():
    email = rand_email()
    pwd = "TestPass@123"
    r = client.post("/api/v1/auth/register", json={
        "full_name": "CFO Chatbot Tester",
        "email": email,
        "password": pwd,
        "business_name": "CFO Analytics Pvt Ltd",
        "gstin": rand_gstin(),
    })
    assert r.status_code in (200, 201)
    user_id = r.json().get("id") or r.json().get("user_id")
    context["user_id"] = user_id

    r_login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    token = r_login.json()["access_token"]
    context["headers"] = {"Authorization": f"Bearer {token}"}

    # Seed 1 customer, 2 invoices, 1 payment
    db = SessionLocal()
    try:
        import uuid
        uid = uuid.UUID(user_id)
        cust = Customer(
            user_id=uid,
            name="Alpha Corp",
            email="finance@alphacorp.in",
            outstanding_balance=Decimal("25000.00"),
        )
        db.add(cust)
        db.flush()

        inv1 = SalesInvoice(
            user_id=uid,
            customer_id=cust.id,
            invoice_number=f"INV-CFO-{random.randint(100, 999)}",
            subtotal=Decimal("20000.00"),
            cgst_total=Decimal("1800.00"),
            sgst_total=Decimal("1800.00"),
            tax_amount=Decimal("3600.00"),
            total_amount=Decimal("23600.00"),
            amount_due=Decimal("0.00"),
            status=InvoiceStatus.PAID,
        )
        inv2 = SalesInvoice(
            user_id=uid,
            customer_id=cust.id,
            invoice_number=f"INV-CFO-{random.randint(1000, 9999)}",
            subtotal=Decimal("25000.00"),
            cgst_total=Decimal("2250.00"),
            sgst_total=Decimal("2250.00"),
            tax_amount=Decimal("4500.00"),
            total_amount=Decimal("29500.00"),
            amount_due=Decimal("29500.00"),
            status=InvoiceStatus.OVERDUE,
        )
        db.add_all([inv1, inv2])
        db.flush()

        pay = Payment(
            user_id=uid,
            sales_invoice_id=inv1.id,
            customer_id=cust.id,
            direction=PaymentDirection.INCOMING,
            amount=Decimal("23600.00"),
            status=PaymentStatus.COMPLETED,
            payment_method=PaymentMethod.UPI,
            transaction_reference=f"UPI-ALPHA-{random.randint(10000, 99999)}",
        )
        db.add(pay)
        db.commit()
    finally:
        db.close()


def t02_tool_revenue_summary():
    import uuid
    db = SessionLocal()
    try:
        res = get_revenue_summary(db, uuid.UUID(context["user_id"]))
        assert res["active_invoice_count"] == 2
        assert res["total_invoiced_inr"] == 53100.00
        assert res["total_paid_inr"] == 23600.00
    finally:
        db.close()


def t03_tool_gst_summary():
    import uuid
    db = SessionLocal()
    try:
        res = get_gst_summary(db, uuid.UUID(context["user_id"]))
        assert res["total_output_tax_inr"] == 8100.00
        assert res["net_tax_payable_inr"] == 8100.00
    finally:
        db.close()


def t04_tool_outstanding_invoices():
    import uuid
    db = SessionLocal()
    try:
        res = get_outstanding_invoices(db, uuid.UUID(context["user_id"]), status="overdue")
        assert res["count"] == 1
        assert res["invoices"][0]["amount_due_inr"] == 29500.00
    finally:
        db.close()


def t05_tool_customer_summary():
    import uuid
    db = SessionLocal()
    try:
        res = get_customer_summary(db, uuid.UUID(context["user_id"]), query_type="highest_due")
        assert res["count"] >= 1
        assert res["customers"][0]["customer_name"] == "Alpha Corp"
    finally:
        db.close()


def t06_tool_payment_history():
    import uuid
    db = SessionLocal()
    try:
        res = get_payment_history(db, uuid.UUID(context["user_id"]), limit=5, direction="incoming")
        assert res["count"] >= 1
        assert res["payments"][0]["amount_inr"] == 23600.00
    finally:
        db.close()


def t07_tool_invoice_stats():
    import uuid
    db = SessionLocal()
    try:
        res = get_invoice_stats(db, uuid.UUID(context["user_id"]))
        assert res["total_invoices"] == 2
        assert res["counts_by_status"]["paid"] == 1
        assert res["counts_by_status"]["overdue"] == 1
    finally:
        db.close()


def t08_api_suggested_questions():
    r = client.get("/api/v1/chatbot/suggested", headers=context["headers"])
    assert r.status_code == 200
    data = r.json()
    assert "categories" in data
    assert "Revenue & Sales" in data["categories"]


def t09_api_ask_chatbot_revenue():
    payload = {"query": "What is my total sales revenue?"}
    r = client.post("/api/v1/chatbot/ask", json=payload, headers=context["headers"])
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert "Rs" in data["answer"] or "₹" in data["answer"] or "53,100" in data["answer"]
    assert data["status"] == "completed"


def t10_api_ask_chatbot_overdue():
    payload = {"query": "Do I have any overdue invoices?"}
    r = client.post("/api/v1/chatbot/ask", json=payload, headers=context["headers"])
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert "Alpha Corp" in data["answer"] or "pending" in data["answer"].lower() or "overdue" in data["answer"].lower()


if __name__ == "__main__":
    print("=" * 65)
    print("  PHASE 7 TEST SUITE - AI VIRTUAL CFO CHATBOT")
    print("=" * 65)
    tests = [
        ("T01  Auth Setup & Database Seeding",       t01_auth_setup_and_seed_data),
        ("T02  Tool: Revenue Summary Query",         t02_tool_revenue_summary),
        ("T03  Tool: GST Summary Query",             t03_tool_gst_summary),
        ("T04  Tool: Outstanding Invoices Query",    t04_tool_outstanding_invoices),
        ("T05  Tool: Customer Summary Query",        t05_tool_customer_summary),
        ("T06  Tool: Payment History Query",         t06_tool_payment_history),
        ("T07  Tool: Invoice Distribution Stats",    t07_tool_invoice_stats),
        ("T08  API: GET /chatbot/suggested",         t08_api_suggested_questions),
        ("T09  API: POST /chatbot/ask (Revenue)",    t09_api_ask_chatbot_revenue),
        ("T10  API: POST /chatbot/ask (Overdue)",    t10_api_ask_chatbot_overdue),
    ]
    for name, fn in tests:
        run(name, fn)
    print("-" * 65)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  Results: {passed} passed  |  {failed} failed  |  {len(results)} total")
    print("-" * 65)
    if failed == 0:
        print("  ALL 10 PHASE 7 TESTS PASSED!")
    sys.exit(0 if failed == 0 else 1)
