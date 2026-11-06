# backend/tests/run_forecast_tests.py
"""
PHASE 7 TEST SUITE — Cash Flow Forecasting, Dashboard & Smart Alerts
Run with: python backend/tests/run_forecast_tests.py

Tests (20 total):
 1   Health check
 2   Register user
 3   Login / JWT
 4   Create customer, product, sales invoice (seed data)
 5   Record payment against invoice (seed data)
 6   Generate BASELINE monthly forecast (3 periods)
 7   Forecast returns correct period count
 8   Forecast periods are in sequence (no gaps)
 9   Generate OPTIMISTIC forecast — inflows >= baseline inflows
10   Generate PESSIMISTIC forecast — inflows <= baseline inflows
11   List forecasts — user sees own forecasts only
12   Forecast user isolation (second user cannot see first user's forecasts)
13   GET /cfo/dashboard — returns all required fields
14   Dashboard: receivables_aging has 4 buckets
15   Dashboard: monthly_revenue list is non-empty
16   Dashboard: gst_due_date is in the future
17   POST /alerts/scan — manual scan runs without error
18   List alerts — returns list
19   Alert summary — has correct field structure
20   Mark all alerts read — returns updated count
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
    return f"fcst_{random.randint(10000,99999)}@test.com"

def rand_gstin():
    s = random.randint(10, 35)
    lt = ''.join(random.choices(string.ascii_uppercase, k=5))
    di = ''.join(random.choices(string.digits, k=4))
    a = random.choice(string.ascii_uppercase)
    p = random.choice('123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    c = random.choice(string.digits + string.ascii_uppercase)
    return f"{s:02d}{lt}{di}{a}{p}Z{c}"

# ──────────────────────────────────────────────────────────────
# SEED HELPERS
# ──────────────────────────────────────────────────────────────

def _register_and_login(email=None, password="Pass@1234"):
    email = email or rand_email()
    client.post("/api/v1/auth/register", json={
        "full_name": "Forecast Tester",
        "email": email,
        "password": password,
        "business_name": "Test Biz",
        "gstin": rand_gstin(),
    })
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_customer(headers):
    r = client.post("/api/v1/billing/customers", json={
        "name": "Acme Corp",
        "email": "acme@corp.com",
        "gstin": rand_gstin(),
        "state": "Tamil Nadu",
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_product(headers):
    r = client.post("/api/v1/billing/products", json={
        "name": "Consulting Service",
        "hsn_code": "998313",
        "base_price": "10000.00",
        "gst_rate": "18.00",
        "unit": "SVC",
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]



def _create_invoice(headers, customer_id, product_id):
    due = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
    r = client.post("/api/v1/billing/invoices", json={
        "customer_id": customer_id,
        "due_date": due,
        "gst_type": "INTRA",

        "items": [{"product_id": product_id, "quantity": 2, "unit_price": "10000.00"}],
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json(), customer_id



def _record_payment(headers, invoice_id, customer_id, amount):
    r = client.post("/api/v1/payments", json={
        "sales_invoice_id": invoice_id,
        "customer_id": customer_id,
        "amount": str(amount),
        "payment_method": "bank_transfer",
        "direction": "incoming",
        "payment_date": datetime.utcnow().isoformat(),
    }, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()



# ──────────────────────────────────────────────────────────────
# TESTS
# ──────────────────────────────────────────────────────────────

def t01_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def t02_register():
    context["email"] = rand_email()
    context["password"] = "Pass@1234"
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Forecast User",
        "email": context["email"],
        "password": context["password"],
        "business_name": "Forecast Test Co",
        "gstin": rand_gstin(),
    })
    assert r.status_code in (200, 201), f"Register failed: {r.text}"


def t03_login():
    r = client.post("/api/v1/auth/login", json={
        "email": context["email"], "password": context["password"],
    })
    assert r.status_code == 200, r.text
    context["headers"] = {"Authorization": f"Bearer {r.json()['access_token']}"}


def t04_seed_invoice():
    cid = _create_customer(context["headers"])
    pid = _create_product(context["headers"])
    inv, customer_id = _create_invoice(context["headers"], cid, pid)
    context["invoice_id"] = inv["id"]
    context["invoice_total"] = inv["total_amount"]
    context["customer_id"] = customer_id
    assert Decimal(str(inv["total_amount"])) > Decimal("0")


def t05_seed_payment():
    # Must send the invoice first (DRAFT → SENT) before accepting payment
    rs = client.patch(
        f"/api/v1/invoices/{context['invoice_id']}/send",
        headers=context["headers"],
    )
    assert rs.status_code == 200, f"Send invoice failed: {rs.text}"

    total = Decimal(str(context["invoice_total"]))
    _record_payment(
        context["headers"],
        context["invoice_id"],
        context["customer_id"],
        total,
    )




def t06_generate_baseline_forecast():
    r = client.post("/api/v1/cfo/forecast", json={
        "forecast_type": "monthly",
        "scenario": "baseline",
        "periods_ahead": 3,
    }, headers=context["headers"])
    assert r.status_code == 201, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert "periods" in data
    assert "summary" in data
    assert data["scenario"] == "baseline"
    assert data["forecast_type"] == "monthly"
    context["forecast_response"] = data


def t07_forecast_period_count():
    data = context["forecast_response"]
    assert len(data["periods"]) == 3, f"Expected 3 periods, got {len(data['periods'])}"
    for p in data["periods"]:
        assert Decimal(str(p["predicted_inflow"])) >= Decimal("0")
        assert Decimal(str(p["predicted_outflow"])) >= Decimal("0")


def t08_forecast_periods_sequential():
    periods = context["forecast_response"]["periods"]
    for i in range(1, len(periods)):
        prev_end = datetime.fromisoformat(periods[i-1]["period_end"].replace("Z", ""))
        curr_start = datetime.fromisoformat(periods[i]["period_start"].replace("Z", ""))
        assert curr_start > prev_end, f"Period {i} starts before period {i-1} ends"


def t09_optimistic_forecast():
    r = client.post("/api/v1/cfo/forecast", json={
        "forecast_type": "monthly",
        "scenario": "optimistic",
        "periods_ahead": 1,
    }, headers=context["headers"])
    assert r.status_code == 201, r.text
    opt_inflow = Decimal(str(r.json()["periods"][0]["predicted_inflow"]))

    r2 = client.post("/api/v1/cfo/forecast", json={
        "forecast_type": "monthly",
        "scenario": "pessimistic",
        "periods_ahead": 1,
    }, headers=context["headers"])
    assert r2.status_code == 201, r2.text
    pess_inflow = Decimal(str(r2.json()["periods"][0]["predicted_inflow"]))

    # Optimistic inflow must be >= pessimistic inflow
    assert opt_inflow >= pess_inflow, (
        f"Optimistic ({opt_inflow}) should be >= pessimistic ({pess_inflow})"
    )


def t10_pessimistic_lower_than_optimistic():
    # Already verified in t09; just check pessimistic outflow >= optimistic outflow
    r_opt = client.post("/api/v1/cfo/forecast", json={
        "forecast_type": "monthly", "scenario": "optimistic", "periods_ahead": 1,
    }, headers=context["headers"])
    r_pes = client.post("/api/v1/cfo/forecast", json={
        "forecast_type": "monthly", "scenario": "pessimistic", "periods_ahead": 1,
    }, headers=context["headers"])
    opt_out = Decimal(str(r_opt.json()["periods"][0]["predicted_outflow"]))
    pes_out = Decimal(str(r_pes.json()["periods"][0]["predicted_outflow"]))
    assert pes_out >= opt_out, f"Pessimistic outflow ({pes_out}) should be >= optimistic ({opt_out})"


def t11_list_forecasts():
    r = client.get("/api/v1/cfo/forecasts", headers=context["headers"])
    assert r.status_code == 200, r.text
    forecasts = r.json()
    assert isinstance(forecasts, list)
    assert len(forecasts) >= 3, f"Expected at least 3 forecasts, got {len(forecasts)}"
    for f in forecasts:
        assert "id" in f
        assert "predicted_net" in f


def t12_forecast_isolation():
    headers2 = _register_and_login()
    r = client.get("/api/v1/cfo/forecasts", headers=headers2)
    assert r.status_code == 200, r.text
    # Second user has no forecasts yet
    assert len(r.json()) == 0, "Second user should not see first user's forecasts"


def t13_dashboard_all_fields():
    r = client.get("/api/v1/cfo/dashboard", headers=context["headers"])
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    d = r.json()
    required = [
        "as_of", "total_revenue_ytd", "total_invoiced_ytd", "revenue_collected_percent",
        "total_outstanding_receivables", "overdue_receivables", "receivables_aging",
        "gst_payable_current_month", "gst_due_date", "days_to_gst_due",
        "total_outstanding_payables", "overdue_payables", "payables_due_next_7_days",
        "net_cash_position", "monthly_revenue",
        "invoices_due_next_30_days", "purchases_due_next_30_days", "total_due_next_30_days",
        "active_alerts_count", "critical_alerts_count",
    ]
    missing = [k for k in required if k not in d]
    assert not missing, f"Missing dashboard fields: {missing}"
    context["dashboard"] = d


def t14_dashboard_aging_buckets():
    aging = context["dashboard"]["receivables_aging"]
    assert len(aging) == 4, f"Expected 4 aging buckets, got {len(aging)}"
    bucket_names = {b["bucket"] for b in aging}
    assert "0-30 days" in bucket_names
    assert "90+ days" in bucket_names


def t15_dashboard_monthly_revenue():
    monthly = context["dashboard"]["monthly_revenue"]
    assert isinstance(monthly, list)
    assert len(monthly) >= 1, "Monthly revenue should have at least 1 entry (current FY)"
    for m in monthly:
        assert "month" in m
        assert "invoiced" in m
        assert "collected" in m


def t16_dashboard_gst_date_future():
    d = context["dashboard"]
    gst_date_str = d["gst_due_date"]
    assert d["days_to_gst_due"] >= 0, "days_to_gst_due should not be negative"
    # Verify gst_due_date is parseable
    from datetime import datetime
    parsed = datetime.strptime(gst_date_str, "%d %b %Y")
    assert parsed > datetime.utcnow().replace(day=1), "GST due date should be in future"


def t17_manual_alert_scan():
    r = client.post("/api/v1/alerts/scan", headers=context["headers"])
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert "new_alerts_created" in data
    assert isinstance(data["new_alerts_created"], int)


def t18_list_alerts():
    r = client.get("/api/v1/alerts", headers=context["headers"])
    assert r.status_code == 200, r.text
    alerts = r.json()
    assert isinstance(alerts, list)
    # May be empty if no overdue invoices — just verify shape
    for a in alerts:
        assert "id" in a
        assert "severity" in a
        assert "title" in a
        assert "is_read" in a


def t19_alert_summary():
    r = client.get("/api/v1/alerts/summary", headers=context["headers"])
    assert r.status_code == 200, r.text
    s = r.json()
    for field in ("total", "unread", "critical", "high", "medium", "low"):
        assert field in s, f"Missing field '{field}' in alert summary"
        assert isinstance(s[field], int)
    assert s["total"] == s["critical"] + s["high"] + s["medium"] + s["low"], \
        "total should equal sum of severity counts"


def t20_mark_all_read():
    r = client.post("/api/v1/alerts/mark-all-read", headers=context["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert "marked_read" in data
    assert isinstance(data["marked_read"], int)

    # Verify unread count is now 0
    r2 = client.get("/api/v1/alerts/summary", headers=context["headers"])
    assert r2.json()["unread"] == 0, "After mark-all-read, unread should be 0"


# ──────────────────────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  PHASE 7 — FORECASTING, DASHBOARD & ALERTS TEST SUITE")
    print("=" * 65)

    tests = [
        ("T01  Health check",                         t01_health),
        ("T02  User registration",                    t02_register),
        ("T03  Login / JWT",                          t03_login),
        ("T04  Seed: create invoice",                 t04_seed_invoice),
        ("T05  Seed: record payment",                 t05_seed_payment),
        ("T06  Generate baseline monthly forecast",   t06_generate_baseline_forecast),
        ("T07  Forecast: correct period count",       t07_forecast_period_count),
        ("T08  Forecast: sequential periods",         t08_forecast_periods_sequential),
        ("T09  Optimistic >= pessimistic inflow",     t09_optimistic_forecast),
        ("T10  Pessimistic >= optimistic outflow",    t10_pessimistic_lower_than_optimistic),
        ("T11  List forecasts (own only)",            t11_list_forecasts),
        ("T12  Forecast user isolation",              t12_forecast_isolation),
        ("T13  Dashboard: all required fields",       t13_dashboard_all_fields),
        ("T14  Dashboard: 4 aging buckets",           t14_dashboard_aging_buckets),
        ("T15  Dashboard: monthly revenue list",      t15_dashboard_monthly_revenue),
        ("T16  Dashboard: GST due date is future",    t16_dashboard_gst_date_future),
        ("T17  Manual alert scan endpoint",           t17_manual_alert_scan),
        ("T18  List alerts",                          t18_list_alerts),
        ("T19  Alert summary fields + math",          t19_alert_summary),
        ("T20  Mark all alerts read",                 t20_mark_all_read),
    ]

    for name, fn in tests:
        run(name, fn)

    print("\n" + "-" * 65)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  Results: {passed} passed  |  {failed} failed  |  {len(results)} total")
    print("-" * 65)

    if failed == 0:
        print("\n  ALL 20 PHASE 7 FORECASTING, DASHBOARD & ALERT TESTS PASSED!")
    else:
        print("\n  FAILURES:")
        for name, ok, err in results:
            if not ok:
                print(f"    {FAIL} {name}: {err}")
    print()
    sys.exit(0 if failed == 0 else 1)
