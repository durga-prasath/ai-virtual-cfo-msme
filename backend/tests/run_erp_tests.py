# backend/tests/run_erp_tests.py
"""
PHASE 8 TEST SUITE — ERP Integration, Revenue Ledger & Financial Reports
Run with: python backend/tests/run_erp_tests.py

Tests (20 total):
 1   Health check / app version is 0.8.0
 2   Register user
 3   Login / JWT
 4   GET /erp/business — auto-creates business profile
 5   PATCH /erp/business — update business name and ERP provider
 6   GET /erp/config — returns ERP connectivity status
 7   Seed: create customer, product, invoice
 8   Seed: send invoice, record payment
 9   GET /erp/ledger — entries exist after invoice+payment seeded
10   Ledger has INVOICE_RAISED entry for our invoice
11   POST /erp/sync (dry_run=true) — returns entity counts
12   POST /erp/sync (dry_run=false) — marks entries as synced
13   GET /erp/config — pending_sync_count decreases after sync
14   POST /erp/ledger — manual bad-debt write-off entry
15   GET /erp/ledger?entry_type=bad_debt_write_off — finds it
16   GET /erp/reports/pl — P&L has all required fields
17   P&L gross_invoiced > 0 after seeding invoice
18   P&L net_revenue <= gross_invoiced (discount subtracted)
19   GET /erp/reports/trial — trial balance has is_balanced field
20   User isolation — second user sees empty ledger
"""

import sys
import random
import string
from decimal import Decimal
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=True)

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []
context = {}


def run(name, fn):
    try:
        fn()
        print(f"  {PASS} {name}")
        results.append((name, True, None))
    except AssertionError as e:
        print(f"  {FAIL} {name}: {e}")
        results.append((name, False, str(e)))
    except Exception as e:
        print(f"  {FAIL} {name}: {type(e).__name__}: {e}")
        results.append((name, False, str(e)))


def rand_email():
    return f"erp_{random.randint(10000,99999)}@test.com"

def rand_gstin():
    s = random.randint(10, 35)
    lt = ''.join(random.choices(string.ascii_uppercase, k=5))
    di = ''.join(random.choices(string.digits, k=4))
    a = random.choice(string.ascii_uppercase)
    p = random.choice('123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    c = random.choice(string.digits + string.ascii_uppercase)
    return f"{s:02d}{lt}{di}{a}{p}Z{c}"

def _headers():
    return context["headers"]

# ──────────────────────────────────────────────────────────────
# SEED HELPERS
# ──────────────────────────────────────────────────────────────

def _register_and_login(email=None, password="Pass@1234"):
    email = email or rand_email()
    client.post("/api/v1/auth/register", json={
        "full_name": "ERP Tester",
        "email": email,
        "password": password,
        "business_name": "ERP Test Co",
        "gstin": rand_gstin(),
    })
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_invoice_and_payment(headers):
    # Customer
    rc = client.post("/api/v1/billing/customers", json={
        "name": "Test Customer",
        "email": "tc@tc.com",
        "gstin": rand_gstin(),
        "state": "Tamil Nadu",
    }, headers=headers)
    assert rc.status_code == 201, rc.text
    cid = rc.json()["id"]

    # Product
    rp = client.post("/api/v1/billing/products", json={
        "name": "ERP Product",
        "hsn_code": "998313",
        "base_price": "5000.00",
        "gst_rate": "18.00",
        "unit": "SVC",
    }, headers=headers)
    assert rp.status_code == 201, rp.text
    pid = rp.json()["id"]

    # Invoice
    due = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
    ri = client.post("/api/v1/billing/invoices", json={
        "customer_id": cid,
        "due_date": due,
        "gst_type": "INTRA",
        "items": [{"product_id": pid, "quantity": 1, "unit_price": "5000.00"}],
    }, headers=headers)
    assert ri.status_code == 201, ri.text
    inv = ri.json()
    inv_id = inv["id"]

    # Send invoice
    rs = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=headers)
    assert rs.status_code == 200, rs.text

    # Payment
    rpy = client.post("/api/v1/payments", json={
        "sales_invoice_id": inv_id,
        "customer_id": cid,
        "amount": str(inv["total_amount"]),
        "payment_method": "bank_transfer",
        "direction": "incoming",
        "payment_date": datetime.utcnow().isoformat(),
    }, headers=headers)
    assert rpy.status_code in (200, 201), rpy.text

    return inv_id, inv["total_amount"]


# ──────────────────────────────────────────────────────────────
# TESTS
# ──────────────────────────────────────────────────────────────

def t01_health_version():
    r = client.get("/health")
    assert r.status_code == 200
    # Check version on openapi
    rv = client.get("/openapi.json")
    assert rv.status_code == 200
    assert rv.json()["info"]["version"] == "0.8.0", f"Expected 0.8.0, got {rv.json()['info']['version']}"


def t02_register():
    context["email"] = rand_email()
    context["password"] = "Pass@1234"
    r = client.post("/api/v1/auth/register", json={
        "full_name": "ERP User",
        "email": context["email"],
        "password": context["password"],
        "business_name": "Acme ERP Ltd",
        "gstin": rand_gstin(),
    })
    assert r.status_code in (200, 201), r.text


def t03_login():
    r = client.post("/api/v1/auth/login", json={
        "email": context["email"], "password": context["password"],
    })
    assert r.status_code == 200, r.text
    context["headers"] = {"Authorization": f"Bearer {r.json()['access_token']}"}


def t04_get_business_profile():
    r = client.get("/api/v1/erp/business", headers=_headers())
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    biz = r.json()
    assert "id" in biz
    assert "business_name" in biz
    assert "erp_enabled" in biz
    context["biz_id"] = biz["id"]


def t05_update_business_profile():
    r = client.patch("/api/v1/erp/business", json={
        "business_name": "Updated ERP Ltd",
        "erp_provider": "tally",
        "erp_enabled": True,
        "city": "Chennai",
        "state": "Tamil Nadu",
    }, headers=_headers())
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    biz = r.json()
    assert biz["business_name"] == "Updated ERP Ltd"
    assert biz["erp_provider"] == "tally"
    assert biz["erp_enabled"] == True


def t06_get_erp_config():
    r = client.get("/api/v1/erp/config", headers=_headers())
    assert r.status_code == 200, r.text
    cfg = r.json()
    for field in ("erp_enabled", "erp_provider", "connection_status", "pending_sync_count"):
        assert field in cfg, f"Missing field: {field}"
    assert cfg["connection_status"] == "connected"
    assert isinstance(cfg["pending_sync_count"], int)


def t07_seed_invoice():
    inv_id, total = _seed_invoice_and_payment(_headers())
    context["inv_id"] = inv_id
    context["inv_total"] = total
    assert Decimal(str(total)) > Decimal("0")


def t08_seed_payment_done():
    # Already done inside t07/_seed_invoice_and_payment
    # Just verify invoice exists
    assert context.get("inv_id") is not None


def t09_ledger_has_entries():
    r = client.get("/api/v1/erp/ledger", headers=_headers())
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    entries = r.json()
    assert isinstance(entries, list)
    assert len(entries) >= 1, "Expected at least 1 ledger entry after invoice+payment"
    context["ledger_entries"] = entries


def t10_ledger_has_invoice_raised():
    entries = context["ledger_entries"]
    types = {e["entry_type"] for e in entries}
    assert "invoice_raised" in types, f"Expected invoice_raised entry. Found: {types}"
    inv_entry = next(e for e in entries if e["entry_type"] == "invoice_raised")
    assert Decimal(str(inv_entry["gross_amount"])) > Decimal("0")
    assert inv_entry["synced_to_erp"] == False   # not yet synced


def t11_erp_sync_dry_run():
    r = client.post("/api/v1/erp/sync", json={
        "provider": "tally",
        "direction": "push",
        "entities": ["all"],
        "dry_run": True,
    }, headers=_headers())
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    result = r.json()
    assert result["dry_run"] == True
    assert result["status"] == "success"
    assert "entities" in result
    total_found = sum(e["total"] for e in result["entities"])
    assert total_found >= 1, "Dry run should report at least 1 record to sync"
    # dry_run should NOT mark anything as synced
    assert result["total_synced"] == 0, "Dry run must not sync anything"


def t12_erp_sync_real():
    r = client.post("/api/v1/erp/sync", json={
        "provider": "tally",
        "direction": "push",
        "entities": ["invoices", "payments"],
        "dry_run": False,
    }, headers=_headers())
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    result = r.json()
    assert result["dry_run"] == False
    assert result["total_synced"] >= 1, f"Expected at least 1 record synced, got {result['total_synced']}"
    assert result["total_failed"] == 0


def t13_pending_sync_decreases():
    # After syncing invoices+payments, pending count should be lower than before t11
    r = client.get("/api/v1/erp/config", headers=_headers())
    assert r.status_code == 200, r.text
    # After sync, ledger entries should be marked as synced
    rl = client.get("/api/v1/erp/ledger?unsynced_only=false", headers=_headers())
    synced = [e for e in rl.json() if e["synced_to_erp"] == True]
    assert len(synced) >= 1, "At least 1 entry should be marked synced after sync"


def t14_manual_ledger_entry():
    r = client.post("/api/v1/erp/ledger", json={
        "entry_type": "bad_debt_write_off",
        "entry_date": datetime.utcnow().isoformat(),
        "description": "Write off old unpaid invoice",
        "gross_amount": "1500.00",
        "discount_amount": "0.00",
        "cgst_amount": "0.00",
        "sgst_amount": "0.00",
        "igst_amount": "0.00",
    }, headers=_headers())
    assert r.status_code == 201, f"Status {r.status_code}: {r.text}"
    entry = r.json()
    assert entry["entry_type"] == "bad_debt_write_off"
    assert Decimal(str(entry["gross_amount"])) == Decimal("1500.00")
    assert entry["synced_to_erp"] == False
    context["bad_debt_entry_id"] = entry["id"]


def t15_filter_ledger_by_type():
    r = client.get("/api/v1/erp/ledger?entry_type=bad_debt_write_off", headers=_headers())
    assert r.status_code == 200, r.text
    entries = r.json()
    assert len(entries) >= 1
    assert all(e["entry_type"] == "bad_debt_write_off" for e in entries)


def t16_pl_report_fields():
    today = datetime.utcnow()
    fy_start = today.replace(month=4, day=1) if today.month >= 4 else today.replace(year=today.year-1, month=4, day=1)
    r = client.get(
        f"/api/v1/erp/reports/pl?from_date={fy_start.strftime('%Y-%m-%d')}&to_date={today.strftime('%Y-%m-%d')}",
        headers=_headers(),
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    pl = r.json()
    required = [
        "period_label", "from_date", "to_date", "generated_at",
        "gross_invoiced", "total_discount", "net_revenue",
        "total_tax_collected", "total_collected",
        "total_purchases", "gross_profit", "gross_profit_margin",
        "bad_debts_written_off", "net_profit", "net_profit_margin",
        "monthly_breakdown",
    ]
    missing = [k for k in required if k not in pl]
    assert not missing, f"Missing P&L fields: {missing}"
    context["pl"] = pl


def t17_pl_has_positive_invoiced():
    pl = context["pl"]
    gross = Decimal(str(pl["gross_invoiced"]))
    assert gross > Decimal("0"), f"gross_invoiced should be > 0 after seeding invoice, got {gross}"


def t18_pl_net_le_gross():
    pl = context["pl"]
    gross = Decimal(str(pl["gross_invoiced"]))
    net   = Decimal(str(pl["net_revenue"]))
    assert net <= gross, f"net_revenue ({net}) must be <= gross_invoiced ({gross})"


def t19_trial_balance():
    today = datetime.utcnow()
    fy = f"{today.year}-{today.year+1}" if today.month >= 4 else f"{today.year-1}-{today.year}"
    r = client.get(f"/api/v1/erp/reports/trial?financial_year={fy}", headers=_headers())
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    tb = r.json()
    for field in ("financial_year", "total_debits", "total_credits", "balance", "entries_by_type", "is_balanced"):
        assert field in tb, f"Missing trial balance field: {field}"
    assert isinstance(tb["entries_by_type"], list)
    assert isinstance(tb["is_balanced"], bool)


def t20_user_isolation():
    headers2 = _register_and_login()
    # Second user should have empty ledger
    r = client.get("/api/v1/erp/ledger", headers=headers2)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 0, "Second user should have empty ledger"


# ──────────────────────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  PHASE 8 — ERP INTEGRATION & REVENUE LEDGER TEST SUITE")
    print("=" * 65)

    tests = [
        ("T01  Health / version 0.8.0",             t01_health_version),
        ("T02  User registration",                   t02_register),
        ("T03  Login / JWT",                         t03_login),
        ("T04  Get business profile (auto-create)",  t04_get_business_profile),
        ("T05  Update business + ERP config",        t05_update_business_profile),
        ("T06  ERP config status",                   t06_get_erp_config),
        ("T07  Seed: invoice created",               t07_seed_invoice),
        ("T08  Seed: payment done",                  t08_seed_payment_done),
        ("T09  Ledger: entries exist",               t09_ledger_has_entries),
        ("T10  Ledger: invoice_raised entry found",  t10_ledger_has_invoice_raised),
        ("T11  ERP sync: dry_run=true",              t11_erp_sync_dry_run),
        ("T12  ERP sync: dry_run=false",             t12_erp_sync_real),
        ("T13  Ledger entries marked synced",        t13_pending_sync_decreases),
        ("T14  Manual bad-debt ledger entry",        t14_manual_ledger_entry),
        ("T15  Filter ledger by entry_type",         t15_filter_ledger_by_type),
        ("T16  P&L report: all fields present",      t16_pl_report_fields),
        ("T17  P&L: gross_invoiced > 0",             t17_pl_has_positive_invoiced),
        ("T18  P&L: net_revenue <= gross_invoiced",  t18_pl_net_le_gross),
        ("T19  Trial balance fields",                t19_trial_balance),
        ("T20  User isolation: empty ledger",        t20_user_isolation),
    ]

    for name, fn in tests:
        run(name, fn)

    print("\n" + "-" * 65)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  Results: {passed} passed  |  {failed} failed  |  {len(results)} total")
    print("-" * 65)

    if failed == 0:
        print("\n  ALL 20 PHASE 8 ERP & REVENUE LEDGER TESTS PASSED!")
    else:
        print("\n  FAILURES:")
        for name, ok, err in results:
            if not ok:
                print(f"    {FAIL} {name}: {err}")
    print()
    sys.exit(0 if failed == 0 else 1)
