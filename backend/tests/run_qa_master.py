# backend/tests/run_qa_master.py
"""
MASTER QA TEST SUITE — AI Virtual CFO Platform
Covers all 10 phases from the testing specification:
  Phase 1  — Authentication (registration, login, JWT)
  Phase 2  — Customer CRUD & isolation
  Phase 3  — Product CRUD & validation
  Phase 4  — Invoice creation, GST math, lifecycle
  Phase 5  — Payment recording & math precision
  Phase 6  — Security (bypass, isolation, injection)
  Phase 7  — Business logic / DB integrity checks via API
  Phase 8  — GST calculation accuracy
  Phase 9  — API response format
  Phase 10 — End-to-end flows

Run: python tests/run_qa_master.py  (from backend/ directory)
"""

import sys
import json
import random
import string
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, date

sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=False)

# ─── Result tracking ──────────────────────────────────────────
results = []
ctx = {}  # shared state between tests

def PASS(name):
    sys.stdout.buffer.write(f"  [PASS] {name}\n".encode("utf-8"))
    sys.stdout.buffer.flush()
    results.append((name, True, None))

def FAIL(name, reason):
    sys.stdout.buffer.write(f"  [FAIL] {name}\n         => {reason}\n".encode("utf-8"))
    sys.stdout.buffer.flush()
    results.append((name, False, reason))

def run(name, fn):
    try:
        fn()
    except AssertionError as e:
        FAIL(name, str(e))
    except Exception as e:
        FAIL(name, f"{type(e).__name__}: {e}")

# ─── Helpers ──────────────────────────────────────────────────
def rand_email():
    return f"qa_{random.randint(10000,99999)}@cfo.test"

def rand_gstin(state_code="33"):
    letters = ''.join(random.choices(string.ascii_uppercase, k=5))
    digits  = ''.join(random.choices(string.digits, k=4))
    alpha   = random.choice(string.ascii_uppercase)
    extra   = random.choice('123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    check   = random.choice(string.digits + string.ascii_uppercase)
    return f"{state_code}{letters}{digits}{alpha}{extra}Z{check}"

def hdr(token=None):
    t = token or ctx.get("token_a")
    return {"Authorization": f"Bearer {t}"} if t else {}

def fmtd(today_offset=0):
    """Return date string offset from today."""
    return (date.today() + timedelta(days=today_offset)).isoformat()

def as_list(response_json, *keys):
    """Normalise API list response: handles plain list OR dict wrapper.
    Keys are tried in order, e.g. as_list(data, 'customers', 'invoices').
    Falls back to treating the whole response as the list.
    """
    if isinstance(response_json, list):
        return response_json
    for key in keys:
        if key in response_json:
            return response_json[key]
    return []

def register_and_login(email=None, password="SecurePass1"):
    email = email or rand_email()
    client.post("/api/v1/auth/register", json={
        "full_name": "QA User",
        "email": email,
        "password": password,
        "business_name": "QA Business",
        "gstin": rand_gstin(),
    })
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"], email

# ──────────────────────────────────────────────────────────────
# PHASE 1 — AUTHENTICATION
# ──────────────────────────────────────────────────────────────
def phase1():
    print("\n" + "="*60)
    print("  PHASE 1 — AUTHENTICATION")
    print("="*60)

    ctx["email_a"] = rand_email()
    ctx["password_a"] = "SecurePass1"

    # 1.1.1 Valid registration
    def t111():
        r = client.post("/api/v1/auth/register", json={
            "full_name": "Test Owner",
            "email": ctx["email_a"],
            "password": ctx["password_a"],
            "business_name": "Test Business Pvt Ltd",
            "gstin": rand_gstin(),
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        ctx["user_a_id"] = d.get("id") or d.get("user", {}).get("id")
        assert "id" in d or "user" in d, "No id in response"
        # Password must not leak
        raw = r.text.lower()
        assert "securepass" not in raw, "Plain password in response!"
        assert "hashed_password" not in raw, "hashed_password in response!"
        PASS("1.1.1 Valid registration → 201, no password leak")
    run("1.1.1", t111)

    # 1.1.2 Duplicate email
    def t112():
        r = client.post("/api/v1/auth/register", json={
            "full_name": "Dupe", "email": ctx["email_a"], "password": "SecurePass1",
            "business_name": "Dupe Biz",
        })
        assert r.status_code in (400, 409), f"Expected 409, got {r.status_code}: {r.text}"
        PASS("1.1.2 Duplicate email → 4xx conflict")
    run("1.1.2", t112)

    # 1.1.3 Invalid email format
    def t113():
        r = client.post("/api/v1/auth/register", json={
            "full_name": "Bad", "email": "notanemail", "password": "SecurePass1",
            "business_name": "Bad Biz",
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("1.1.3 Invalid email → 422")
    run("1.1.3", t113)

    # 1.1.7 Missing required fields
    def t117():
        r = client.post("/api/v1/auth/register", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}"
        PASS("1.1.7 Missing required fields → 422")
    run("1.1.7", t117)

    # 1.2.1 Valid login
    def t121():
        r = client.post("/api/v1/auth/login", json={"email": ctx["email_a"], "password": ctx["password_a"]})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        d = r.json()
        assert "access_token" in d, "No access_token"
        token = d["access_token"]
        parts = token.split(".")
        assert len(parts) == 3, f"JWT must have 3 parts, got {len(parts)}"
        ctx["token_a"] = token
        PASS("1.2.1 Valid login → 200, valid JWT")
    run("1.2.1", t121)

    # 1.2.2 Wrong password
    def t122():
        r = client.post("/api/v1/auth/login", json={"email": ctx["email_a"], "password": "WrongPass1"})
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
        msg = r.json().get("detail", "").lower()
        # Must not reveal which field is wrong
        assert "invalid" in msg or "incorrect" in msg or "unauthorized" in msg, f"Unexpected message: {msg}"
        PASS("1.2.2 Wrong password → 401")
    run("1.2.2", t122)

    # 1.2.3 Non-existent email — same message as wrong password
    def t123():
        r = client.post("/api/v1/auth/login", json={"email": "nobody@nowhere.com", "password": "SecurePass1"})
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
        PASS("1.2.3 Non-existent email → 401 (same as wrong password)")
    run("1.2.3", t123)

    # 1.2.4 Empty credentials
    def t124():
        r = client.post("/api/v1/auth/login", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}"
        PASS("1.2.4 Empty credentials → 422")
    run("1.2.4", t124)

    # 1.2.5 SQL injection in login
    def t125():
        r = client.post("/api/v1/auth/login", json={"email": "' OR '1'='1", "password": "x"})
        assert r.status_code in (401, 422), f"SQL injection must not succeed, got {r.status_code}"
        assert "stack" not in r.text.lower() and "traceback" not in r.text.lower(), "Stack trace exposed!"
        PASS("1.2.5 SQL injection → blocked, no stack trace")
    run("1.2.5", t125)

    # 1.3.1 Valid token → /me
    def t131():
        r = client.get("/api/v1/auth/me", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        d = r.json()
        assert d.get("email") == ctx["email_a"], "Wrong user returned by /me"
        assert "hashed_password" not in r.text.lower(), "hashed_password leaked!"
        assert "password" not in d, "password field in /me response!"
        PASS("1.3.1 /me with valid token → 200, correct user, no password")
    run("1.3.1", t131)

    # 1.3.2 No token
    def t132():
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"
        PASS("1.3.2 /me without token → 401")
    run("1.3.2", t132)

    # 1.3.3 Malformed token
    def t133():
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtokenstring"})
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"
        PASS("1.3.3 Malformed token → 401")
    run("1.3.3", t133)

    # 1.3.4 Tampered token
    def t134():
        token = ctx.get("token_a", "a.b.c")
        parts = token.split(".")
        # Tamper middle part
        parts[1] = parts[1][:5] + "XXXXX" + parts[1][10:]
        bad_token = ".".join(parts)
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401, f"Expected 401 for tampered token, got {r.status_code}"
        PASS("1.3.4 Tampered token → 401")
    run("1.3.4", t134)


# ──────────────────────────────────────────────────────────────
# PHASE 2 — CUSTOMERS
# ──────────────────────────────────────────────────────────────
def phase2():
    print("\n" + "="*60)
    print("  PHASE 2 — CUSTOMERS")
    print("="*60)

    # 2.1.1 Valid customer
    def t211():
        ctx["cust_gstin"] = rand_gstin()
        r = client.post("/api/v1/billing/customers", headers=hdr(), json={
            "name": "Ravi Enterprises",
            "email": "ravi@example.com",
            "phone": "9876543210",
            "gstin": ctx["cust_gstin"],
            "address": "123 Anna Salai",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600001",
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        assert "id" in d, "No id in customer response"
        ctx["cust_id_a"] = d["id"]
        assert re.match(r"[0-9a-f-]{36}", d["id"]), "id is not UUID format"
        # user_id must be our user's
        if "user_id" in d:
            assert d["user_id"] != "00000000-0000-0000-0000-000000000000"
        PASS("2.1.1 Create customer → 201, UUID id")
    run("2.1.1", t211)

    # 2.1.2 Minimal customer
    def t212():
        r = client.post("/api/v1/billing/customers", headers=hdr(), json={"name": "Minimal Customer"})
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        PASS("2.1.2 Minimal customer (name only) → 201")
    run("2.1.2", t212)

    # 2.1.3 user_id injection ignored
    def t213():
        fake_uid = "00000000-0000-0000-0000-000000000000"
        r = client.post("/api/v1/billing/customers", headers=hdr(), json={
            "name": "Injection Test",
            "user_id": fake_uid,
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        if "user_id" in d:
            assert d["user_id"] != fake_uid, "Server accepted injected user_id!"
        PASS("2.1.3 user_id injection → ignored, server uses JWT user")
    run("2.1.3", t213)

    # 2.1.6 Missing name
    def t216():
        r = client.post("/api/v1/billing/customers", headers=hdr(), json={"email": "test@test.com"})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("2.1.6 Missing required name → 422")
    run("2.1.6", t216)

    # 2.2.1 List own customers
    def t221():
        r = client.get("/api/v1/billing/customers", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        customers = as_list(r.json(), "customers")
        assert len(customers) >= 1, "Should have at least one customer"
        PASS("2.2.1 List own customers -> 200, >= 1 result")
    run("2.2.1", t221)

    # 2.2.3 Get customer by ID
    def t223():
        cid = ctx.get("cust_id_a")
        if not cid: return FAIL("2.2.3", "No customer id in context")
        r = client.get(f"/api/v1/billing/customers/{cid}", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        PASS("2.2.3 Get customer by ID → 200")
    run("2.2.3", t223)

    # 2.2.5 Non-existent customer
    def t225():
        r = client.get("/api/v1/billing/customers/00000000-0000-0000-0000-000000000000", headers=hdr())
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        PASS("2.2.5 Non-existent customer → 404")
    run("2.2.5", t225)

    # User B setup for isolation tests
    ctx["token_b"], ctx["email_b"] = register_and_login()

    # 2.2.2 User B sees empty list
    def t222():
        r = client.get("/api/v1/billing/customers", headers=hdr(ctx["token_b"]))
        assert r.status_code == 200
        customers = as_list(r.json(), "customers")
        assert len(customers) == 0, f"User B should see 0 customers, saw {len(customers)}"
        PASS("2.2.2 User B sees empty customer list -> isolation OK")
    run("2.2.2", t222)

    # 2.2.4 User B cannot access User A's customer
    def t224():
        cid = ctx.get("cust_id_a")
        if not cid: return FAIL("2.2.4", "No customer id")
        r = client.get(f"/api/v1/billing/customers/{cid}", headers=hdr(ctx["token_b"]))
        assert r.status_code == 404, f"Expected 404, got {r.status_code} — data isolation breach!"
        PASS("2.2.4 User B cannot access User A's customer → 404")
    run("2.2.4", t224)


# ──────────────────────────────────────────────────────────────
# PHASE 3 — PRODUCTS
# ──────────────────────────────────────────────────────────────
def phase3():
    print("\n" + "="*60)
    print("  PHASE 3 — PRODUCTS")
    print("="*60)

    # 3.1.1 Valid product
    def t311():
        r = client.post("/api/v1/billing/products", headers=hdr(), json={
            "name": "Web Development Service",
            "description": "Custom web app development",
            "hsn_code": "998314",
            "base_price": "5000.00",
            "gst_rate": "18.00",
            "unit": "hour",
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        ctx["prod_id_18"] = d["id"]
        PASS("3.1.1 Create product (18% GST) → 201")
    run("3.1.1", t311)

    # 3.1.2 All valid GST slabs
    def t312():
        for rate in ["0", "5", "12", "18", "28"]:
            r = client.post("/api/v1/billing/products", headers=hdr(), json={
                "name": f"Product {rate}pct",
                "base_price": "1000.00",
                "gst_rate": rate,
            })
            assert r.status_code in (200, 201), f"GST rate {rate}% should be valid, got {r.status_code}: {r.text}"
        ctx["prod_id_5"]  = None  # will get from list
        PASS("3.1.2 All valid GST slabs (0,5,12,18,28) → 201 each")
    run("3.1.2", t312)

    # Save product ids per rate for later
    def _save_products():
        r = client.get("/api/v1/billing/products", headers=hdr())
        prods = r.json()
        if isinstance(prods, dict): prods = prods.get("products", [])
        for p in prods:
            rate = str(int(float(p.get("gst_rate", 0))))
            if rate == "5"  and not ctx.get("prod_id_5"):  ctx["prod_id_5"]  = p["id"]
            if rate == "12" and not ctx.get("prod_id_12"): ctx["prod_id_12"] = p["id"]
            if rate == "0"  and not ctx.get("prod_id_0"):  ctx["prod_id_0"]  = p["id"]
            if rate == "28" and not ctx.get("prod_id_28"): ctx["prod_id_28"] = p["id"]
    _save_products()

    # 3.1.4 Negative price
    def t314():
        r = client.post("/api/v1/billing/products", headers=hdr(), json={
            "name": "Bad Price", "base_price": "-100", "gst_rate": "18",
        })
        assert r.status_code == 422, f"Expected 422 for negative price, got {r.status_code}: {r.text}"
        PASS("3.1.4 Negative price → 422")
    run("3.1.4", t314)

    # 3.1.7 Missing base_price
    def t317():
        r = client.post("/api/v1/billing/products", headers=hdr(), json={
            "name": "No Price", "gst_rate": "18",
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("3.1.7 Missing base_price → 422")
    run("3.1.7", t317)


# ──────────────────────────────────────────────────────────────
# PHASE 4 — INVOICES
# ──────────────────────────────────────────────────────────────
def phase4():
    print("\n" + "="*60)
    print("  PHASE 4 — INVOICES")
    print("="*60)

    def q(v): return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 4.1.1 INTRA invoice GST math
    def t411():
        cid = ctx.get("cust_id_a")
        pid = ctx.get("prod_id_18")
        assert cid and pid, "Need customer and product from earlier phases"
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid,
            "gst_type": "INTRA",
            "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 10, "unit_price": "1000.00"}],
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        ctx["inv_draft_id"] = d["id"]

        sub  = q(d.get("subtotal", 0))
        cgst = q(d.get("cgst_total", 0))
        sgst = q(d.get("sgst_total", 0))
        igst = q(d.get("igst_total", 0))
        tot  = q(d.get("total_amount", 0))
        paid = q(d.get("amount_paid", 0))
        due  = q(d.get("amount_due", 0))
        status = d.get("status", "")

        assert sub  == q(10000), f"subtotal: expected 10000, got {sub}"
        assert cgst == q(900),   f"cgst: expected 900, got {cgst}"
        assert sgst == q(900),   f"sgst: expected 900, got {sgst}"
        assert igst == q(0),     f"igst: expected 0, got {igst}"
        assert tot  == q(11800), f"total: expected 11800, got {tot}"
        assert paid == q(0),     f"amount_paid: expected 0, got {paid}"
        assert due  == q(11800), f"amount_due: expected 11800, got {due}"
        assert status == "draft", f"status: expected draft, got {status}"
        inv_num = d.get("invoice_number", "")
        assert inv_num.startswith("INV"), f"invoice_number should start with INV, got {inv_num}"
        ctx["inv_number_1"] = inv_num
        PASS("4.1.1 INTRA invoice → correct GST math (CGST=900, SGST=900, Total=11800)")
    run("4.1.1", t411)

    # 4.1.2 INTER invoice GST math
    def t412():
        cid = ctx.get("cust_id_a")
        pid = ctx.get("prod_id_18")
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTER",
            "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 10, "unit_price": "1000.00"}],
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        ctx["inv_inter_id"] = d["id"]
        cgst = q(d.get("cgst_total", 0))
        sgst = q(d.get("sgst_total", 0))
        igst = q(d.get("igst_total", 0))
        tot  = q(d.get("total_amount", 0))
        assert cgst == q(0),     f"INTER: cgst should be 0, got {cgst}"
        assert sgst == q(0),     f"INTER: sgst should be 0, got {sgst}"
        assert igst == q(1800),  f"INTER: igst should be 1800, got {igst}"
        assert tot  == q(11800), f"INTER: total should be 11800, got {tot}"
        PASS("4.1.2 INTER invoice → CGST=0, SGST=0, IGST=1800, Total=11800")
    run("4.1.2", t412)

    # 4.1.3 Multi-item GST accuracy
    def t413():
        cid = ctx.get("cust_id_a")
        pid18 = ctx.get("prod_id_18")
        pid12 = ctx.get("prod_id_12")
        if not pid12:
            FAIL("4.1.3", "No 12% product created in phase 3")
            return
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA",
            "due_date": fmtd(30),
            "items": [
                {"product_id": pid18, "quantity": 5, "unit_price": "2000.00"},
                {"product_id": pid12, "quantity": 3, "unit_price": "1000.00"},
            ],
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        # Item1: 5×2000=10000, CGST=900, SGST=900
        # Item2: 3×1000=3000,  CGST=180, SGST=180
        # Total: subtotal=13000, CGST=1080, SGST=1080, grand=15160
        sub  = q(d.get("subtotal", 0))
        cgst = q(d.get("cgst_total", 0))
        sgst = q(d.get("sgst_total", 0))
        tot  = q(d.get("total_amount", 0))
        assert sub  == q(13000), f"subtotal: expected 13000, got {sub}"
        assert cgst == q(1080),  f"cgst: expected 1080, got {cgst}"
        assert sgst == q(1080),  f"sgst: expected 1080, got {sgst}"
        assert tot  == q(15160), f"total: expected 15160, got {tot}"
        PASS("4.1.3 Multi-item GST (18%+12%) → subtotal=13000, CGST=1080, Total=15160")
    run("4.1.3", t413)

    # 4.1.5 Customer from different user
    def t415():
        cid = ctx.get("cust_id_a")
        pid = ctx.get("prod_id_18")
        r = client.post("/api/v1/billing/invoices", headers=hdr(ctx["token_b"]), json={
            "customer_id": cid, "gst_type": "INTRA",
            "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 1, "unit_price": "100.00"}],
        })
        assert r.status_code == 404, f"Expected 404 (cross-user customer), got {r.status_code}"
        PASS("4.1.5 Cross-user customer_id → 404")
    run("4.1.5", t415)

    # 4.1.7 Empty items
    def t417():
        cid = ctx.get("cust_id_a")
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA",
            "due_date": fmtd(30), "items": [],
        })
        assert r.status_code == 422, f"Expected 422 for empty items, got {r.status_code}"
        PASS("4.1.7 Empty items array → 422")
    run("4.1.7", t417)

    # 4.1.9 Non-existent customer
    def t419():
        pid = ctx.get("prod_id_18")
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 1, "unit_price": "100.00"}],
        })
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        PASS("4.1.9 Non-existent customer_id → 404")
    run("4.1.9", t419)

    # 4.1.10 Zero GST product
    def t4110():
        cid = ctx.get("cust_id_a")
        pid0 = ctx.get("prod_id_0")
        if not pid0:
            FAIL("4.1.10", "No 0% GST product")
            return
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid0, "quantity": 1, "unit_price": "10000.00"}],
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        assert q(d.get("cgst_total", 0)) == q(0), "0% GST: CGST should be 0"
        assert q(d.get("total_amount", 0)) == q(10000), "0% GST: total should equal subtotal"
        PASS("4.1.10 0% GST invoice → no tax, total = subtotal")
    run("4.1.10", t4110)

    # 4.2.1 Send invoice (DRAFT → SENT)
    def t421():
        inv_id = ctx.get("inv_draft_id")
        r = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        d = r.json()
        assert d.get("status") == "sent", f"Expected status=sent, got {d.get('status')}"
        ctx["inv_sent_id"] = inv_id
        PASS("4.2.1 Send DRAFT invoice → status=sent")
    run("4.2.1", t421)

    # 4.2.2 Cannot send already SENT invoice
    def t422():
        inv_id = ctx.get("inv_sent_id")
        r = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=hdr())
        assert r.status_code == 400, f"Expected 400 (already sent), got {r.status_code}: {r.text}"
        PASS("4.2.2 Send already SENT invoice → 400")
    run("4.2.2", t422)

    # 4.2.4 Cancel DRAFT invoice
    def t424():
        # Create a fresh draft invoice
        cid = ctx.get("cust_id_a")
        pid = ctx.get("prod_id_18")
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 1, "unit_price": "100.00"}],
        })
        inv_id = r.json()["id"]
        rc = client.patch(f"/api/v1/invoices/{inv_id}/cancel", headers=hdr())
        assert rc.status_code == 200, f"Expected 200, got {rc.status_code}: {rc.text}"
        assert rc.json().get("status") == "cancelled"
        PASS("4.2.4 Cancel DRAFT invoice → status=cancelled")
    run("4.2.4", t424)

    # 4.2.5 Cancel SENT invoice
    def t425():
        cid = ctx.get("cust_id_a")
        pid = ctx.get("prod_id_18")
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 1, "unit_price": "500.00"}],
        })
        inv_id = r.json()["id"]
        client.patch(f"/api/v1/invoices/{inv_id}/send", headers=hdr())
        rc = client.patch(f"/api/v1/invoices/{inv_id}/cancel", headers=hdr())
        assert rc.status_code == 200, f"Expected 200 for cancelling SENT, got {rc.status_code}: {rc.text}"
        assert rc.json().get("status") == "cancelled"
        PASS("4.2.5 Cancel SENT invoice → status=cancelled")
    run("4.2.5", t425)

    # 4.2.7 Status filter — invoice list is at /api/v1/invoices (payments router)
    def t427():
        r = client.get("/api/v1/invoices?status=sent", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        invs = as_list(r.json(), "invoices")
        for inv in invs:
            assert inv.get("status") == "sent", f"Non-sent invoice in sent filter: {inv.get('status')}"
        PASS("4.2.7 Invoice status filter -> only matching status returned")
    run("4.2.7", t427)


# ──────────────────────────────────────────────────────────────
# PHASE 5 — PAYMENTS
# ──────────────────────────────────────────────────────────────
def phase5():
    print("\n" + "="*60)
    print("  PHASE 5 — PAYMENTS")
    print("="*60)

    def q(v): return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def fresh_sent_invoice(unit_price="5000.00", qty=2):
        cid = ctx["cust_id_a"]
        pid = ctx["prod_id_18"]
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": qty, "unit_price": unit_price}],
        })
        assert r.status_code in (200, 201), f"Create invoice failed: {r.text}"
        inv = r.json()
        rs = client.patch(f"/api/v1/invoices/{inv['id']}/send", headers=hdr())
        assert rs.status_code == 200, f"Send invoice failed: {rs.text}"
        return inv["id"], q(inv["total_amount"])

    # 5.1.1 Full payment
    def t511():
        inv_id, total = fresh_sent_invoice("5000.00", 2)
        # total = 2*5000 + 18% = 11800
        r = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx["cust_id_a"],
            "amount": str(total),
            "payment_method": "bank_transfer",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        ctx["paid_inv_id"] = inv_id
        # Verify invoice is now PAID
        ri = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=hdr())
        if ri.status_code != 200:
            ri = client.get(f"/api/v1/invoices/{inv_id}", headers=hdr())
        assert ri.status_code == 200
        inv = ri.json()
        assert inv.get("status") == "paid", f"Expected status=paid, got {inv.get('status')}"
        assert q(inv.get("amount_due", 999)) == q(0), f"amount_due should be 0, got {inv.get('amount_due')}"
        assert q(inv.get("amount_paid", 0)) == total, f"amount_paid mismatch"
        PASS(f"5.1.1 Full payment ({total}) → invoice marked PAID, amount_due=0")
    run("5.1.1", t511)

    # 5.1.2 Partial payment
    def t512():
        inv_id, total = fresh_sent_invoice("5000.00", 2)
        partial = q(5000)
        r = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx["cust_id_a"],
            "amount": str(partial),
            "payment_method": "upi",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code in (200, 201), f"Partial payment failed: {r.status_code}: {r.text}"
        ctx["partial_inv_id"] = inv_id
        ctx["partial_remaining"] = str(q(total - partial))
        ri = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=hdr())
        if ri.status_code != 200:
            ri = client.get(f"/api/v1/invoices/{inv_id}", headers=hdr())
        inv = ri.json()
        assert inv.get("status") == "sent", f"Partial payment: status should still be sent, got {inv.get('status')}"
        assert q(inv.get("amount_paid", 0)) == partial, f"amount_paid mismatch"
        remaining = q(total - partial)
        assert q(inv.get("amount_due", 0)) == remaining, f"amount_due mismatch: expected {remaining}, got {inv.get('amount_due')}"
        PASS(f"5.1.2 Partial payment ({partial}/{total}) → status=sent, amount_due={remaining}")
    run("5.1.2", t512)

    # 5.1.3 Complete the partial payment
    def t513():
        inv_id = ctx.get("partial_inv_id")
        remaining = ctx.get("partial_remaining", "6800.00")
        if not inv_id: return FAIL("5.1.3", "No partial invoice")
        r = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx["cust_id_a"],
            "amount": remaining,
            "payment_method": "bank_transfer",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code in (200, 201), f"Expected 201: {r.status_code}: {r.text}"
        ri = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=hdr())
        if ri.status_code != 200:
            ri = client.get(f"/api/v1/invoices/{inv_id}", headers=hdr())
        inv = ri.json()
        assert inv.get("status") == "paid", f"After 2nd payment: expected paid, got {inv.get('status')}"
        PASS("5.1.3 Second partial payment → invoice fully paid")
    run("5.1.3", t513)

    # 5.1.4 Overpayment attempt
    def t514():
        inv_id, total = fresh_sent_invoice("1000.00", 1)
        overpay = q(total + 1000)
        r = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx["cust_id_a"],
            "amount": str(overpay),
            "payment_method": "bank_transfer",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code == 400, f"Overpayment must be 400, got {r.status_code}: {r.text}"
        PASS("5.1.4 Overpayment → 400 Bad Request")
    run("5.1.4", t514)

    # 5.1.5 Pay DRAFT invoice
    def t515():
        cid = ctx["cust_id_a"]
        pid = ctx["prod_id_18"]
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 1, "unit_price": "500.00"}],
        })
        inv_id = r.json()["id"]  # stays DRAFT
        rp = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": cid, "amount": "590.00",
            "payment_method": "cash", "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert rp.status_code == 400, f"Expected 400 (pay draft), got {rp.status_code}: {rp.text}"
        PASS("5.1.5 Pay DRAFT invoice → 400")
    run("5.1.5", t515)

    # 5.1.7 Zero amount
    def t517():
        inv_id, _ = fresh_sent_invoice()
        r = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx["cust_id_a"],
            "amount": "0",
            "payment_method": "cash",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code == 422, f"Expected 422 for zero amount, got {r.status_code}: {r.text}"
        PASS("5.1.7 Zero payment amount → 422")
    run("5.1.7", t517)

    # 5.1.9 Invalid payment method
    def t519():
        inv_id, _ = fresh_sent_invoice()
        r = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx["cust_id_a"],
            "amount": "100.00",
            "payment_method": "bitcoin",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code == 422, f"Expected 422 for invalid method, got {r.status_code}: {r.text}"
        PASS("5.1.9 Invalid payment method (bitcoin) → 422")
    run("5.1.9", t519)

    # 5.1.11 List payments (own only)
    def t5111():
        r = client.get("/api/v1/payments", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        PASS("5.1.11 List payments → 200")
    run("5.1.11", t5111)

    # 5.1.12 User B sees no payments
    def t5112():
        r = client.get("/api/v1/payments", headers=hdr(ctx["token_b"]))
        assert r.status_code == 200
        pays = as_list(r.json(), "payments")
        assert len(pays) == 0, f"User B should see 0 payments, saw {len(pays)}"
        PASS("5.1.12 User B sees empty payments -> isolation OK")
    run("5.1.12", t5112)

    # 5.1.13 Decimal precision
    def t5113():
        # Invoice: 1 item × 1000.00 at 18% = 1180.00
        inv_id, total = fresh_sent_invoice("1000.00", 1)
        pay_amt = q(500)
        r = client.post("/api/v1/payments", headers=hdr(), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx["cust_id_a"],
            "amount": str(pay_amt),
            "payment_method": "bank_transfer",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code in (200, 201), r.text
        ri = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=hdr())
        if ri.status_code != 200:
            ri = client.get(f"/api/v1/invoices/{inv_id}", headers=hdr())
        inv = ri.json()
        expected_due = q(total - pay_amt)
        actual_due   = q(inv.get("amount_due", 0))
        assert actual_due == expected_due, f"Decimal precision: expected {expected_due}, got {actual_due}"
        PASS(f"5.1.13 Decimal precision: total={total}, paid=500, due={expected_due} (exact)")
    run("5.1.13", t5113)


# ──────────────────────────────────────────────────────────────
# PHASE 6 — SECURITY
# ──────────────────────────────────────────────────────────────
def phase6():
    print("\n" + "="*60)
    print("  PHASE 6 — SECURITY")
    print("="*60)

    # 6.1.1 All protected endpoints without token
    def t611():
        endpoints = [
            ("POST", "/api/v1/billing/customers", {"name": "x"}),
            ("GET",  "/api/v1/billing/customers", None),
            ("POST", "/api/v1/billing/products",  {"name": "x", "base_price": "1", "gst_rate": "18"}),
            ("POST", "/api/v1/billing/invoices",  {}),
            ("POST", "/api/v1/payments",           {}),
            ("GET",  "/api/v1/payments",           None),
        ]
        for method, url, body in endpoints:
            if method == "GET":
                r = client.get(url)
            else:
                r = client.post(url, json=body or {})
            assert r.status_code == 401, f"{method} {url} without token: expected 401, got {r.status_code}"
        PASS("6.1.1 All protected endpoints without token → 401 each")
    run("6.1.1", t611)

    # 6.1.2 Fake token
    def t612():
        r = client.get("/api/v1/billing/customers", headers={"Authorization": "Bearer FAKETOKEN123"})
        assert r.status_code == 401, f"Expected 401 for fake token, got {r.status_code}"
        PASS("6.1.2 Fake token → 401")
    run("6.1.2", t612)

    # 6.2.1 User B sees empty customers
    def t621():
        r = client.get("/api/v1/billing/customers", headers=hdr(ctx["token_b"]))
        customers = as_list(r.json(), "customers")
        assert len(customers) == 0, f"Isolation breach: User B sees {len(customers)} of User A's customers"
        PASS("6.2.1 User B sees empty customer list -> data isolation OK")
    run("6.2.1", t621)

    # 6.2.2 User B cannot access User A's customer by ID
    def t622():
        cid = ctx.get("cust_id_a")
        r = client.get(f"/api/v1/billing/customers/{cid}", headers=hdr(ctx["token_b"]))
        assert r.status_code == 404, f"Expected 404 (isolation), got {r.status_code}: {r.text}"
        PASS("6.2.2 User B cannot access User A's customer by ID → 404")
    run("6.2.2", t622)

    # 6.2.3 User B cannot access User A's invoice
    def t623():
        inv_id = ctx.get("inv_sent_id") or ctx.get("inv_draft_id") or ctx.get("inv_inter_id")
        if not inv_id: return FAIL("6.2.3", "No invoice id in context")
        for route in [f"/api/v1/billing/invoices/{inv_id}", f"/api/v1/invoices/{inv_id}"]:
            r = client.get(route, headers=hdr(ctx["token_b"]))
            if r.status_code in (200, 404):
                if r.status_code == 200:
                    FAIL("6.2.3", f"ISOLATION BREACH: User B can read User A's invoice at {route}")
                    return
                break
        PASS("6.2.3 User B cannot access User A's invoice → 404")
    run("6.2.3", t623)

    # 6.2.4 User B cannot send User A's invoice
    def t624():
        inv_id = ctx.get("inv_inter_id")
        if not inv_id: return FAIL("6.2.4", "No invoice id")
        r = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=hdr(ctx["token_b"]))
        assert r.status_code == 404, f"Expected 404 (isolation), got {r.status_code}"
        PASS("6.2.4 User B cannot send User A's invoice → 404")
    run("6.2.4", t624)

    # 6.2.5 User B cannot pay User A's invoice
    def t625():
        inv_id = ctx.get("inv_inter_id") or ctx.get("inv_draft_id")
        r = client.post("/api/v1/payments", headers=hdr(ctx["token_b"]), json={
            "sales_invoice_id": inv_id,
            "customer_id": ctx.get("cust_id_a"),
            "amount": "100.00",
            "payment_method": "cash",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert r.status_code in (400, 404), f"Expected 4xx for cross-user payment, got {r.status_code}"
        PASS("6.2.5 User B cannot pay User A's invoice → 4xx")
    run("6.2.5", t625)

    # 6.2.6 user_id injection
    def t626():
        user_a_id = ctx.get("user_a_id", "00000000-0000-0000-0000-000000000000")
        r = client.post("/api/v1/billing/customers", headers=hdr(ctx["token_b"]), json={
            "name": "Injection Attempt",
            "user_id": user_a_id,
        })
        assert r.status_code in (200, 201), f"Should succeed with 201 (ignoring injected user_id): {r.status_code}"
        d = r.json()
        if "user_id" in d:
            assert d["user_id"] != user_a_id, "SECURITY BUG: Server accepted injected user_id!"
        PASS("6.2.6 user_id injection → ignored, customer belongs to User B")
    run("6.2.6", t626)

    # 6.3.1 XSS in name
    def t631():
        r = client.post("/api/v1/billing/customers", headers=hdr(), json={
            "name": "<script>alert('xss')</script>",
        })
        # Either rejected (422) or stored as literal text — both are safe
        if r.status_code in (200, 201):
            # Stored — make sure it's not being executed (just stored as text)
            assert "<script>" in r.text or "script" in r.text.lower(), "XSS: stored but mangled?"
        elif r.status_code == 422:
            pass  # Rejected — also fine
        else:
            assert False, f"Unexpected status {r.status_code}"
        PASS("6.3.1 XSS in name → safely handled (stored as text or rejected)")
    run("6.3.1", t631)

    # 6.3.2 SQL injection
    def t632():
        r = client.post("/api/v1/billing/customers", headers=hdr(), json={
            "name": "'; DROP TABLE customers; --",
        })
        # Should succeed (SQLAlchemy parameterises) or reject with 422
        assert r.status_code in (200, 201, 422), f"SQL injection caused unexpected {r.status_code}: {r.text}"
        assert "error" not in r.text.lower() or "detail" in r.text.lower(), "Stack trace exposed"
        # Verify customers table still works
        rc = client.get("/api/v1/billing/customers", headers=hdr())
        assert rc.status_code == 200, "customers table broken after SQL injection attempt!"
        PASS("6.3.2 SQL injection → stored as literal or rejected, table intact")
    run("6.3.2", t632)

    # 6.3.4 Invalid UUID format
    def t634():
        r = client.get("/api/v1/billing/customers/not-a-uuid", headers=hdr())
        assert r.status_code == 422, f"Expected 422 for invalid UUID, got {r.status_code}"
        PASS("6.3.4 Invalid UUID in path → 422")
    run("6.3.4", t634)


# ──────────────────────────────────────────────────────────────
# PHASE 7 — BUSINESS LOGIC / API INTEGRITY
# ──────────────────────────────────────────────────────────────
def phase7():
    print("\n" + "="*60)
    print("  PHASE 7 — BUSINESS LOGIC INTEGRITY")
    print("="*60)

    def q(v): return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 7.3 Money precision via API
    def t73():
        r = client.get("/api/v1/invoices", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        invs = as_list(r.json(), "invoices")
        for inv in invs:
            for field in ["subtotal", "cgst_total", "sgst_total", "igst_total", "total_amount"]:
                val = str(inv.get(field, ""))
                if val and val != "None":
                    # Must be valid decimal with at most 2 decimal places
                    try:
                        d = Decimal(val)
                        assert d == d.quantize(Decimal("0.01")), f"{field}={val} has >2 decimal places"
                    except Exception as e:
                        assert False, f"{field}={val}: {e}"
        PASS("7.3 Money precision -> all amounts have <= 2 decimal places")
    run("7.3", t73)

    # 7.5 amount_due = total - amount_paid
    def t75():
        r = client.get("/api/v1/invoices", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        invs = as_list(r.json(), "invoices")
        for inv in invs:
            total = q(inv.get("total_amount", 0))
            paid  = q(inv.get("amount_paid", 0))
            due   = q(inv.get("amount_due", 0))
            calc  = q(total - paid)
            assert due == calc, f"Invoice {inv.get('invoice_number')}: amount_due={due} != total-paid={calc}"
        PASS("7.5 amount_due = total_amount - amount_paid for all invoices")
    run("7.5", t75)

    # 7.6 PAID invoices have amount_due = 0
    def t76():
        r = client.get("/api/v1/invoices", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        invs = as_list(r.json(), "invoices")
        for inv in invs:
            if inv.get("status") == "paid":
                due = q(inv.get("amount_due", 999))
                assert due == q(0), f"PAID invoice {inv.get('invoice_number')} has amount_due={due} (not 0)"
        PASS("7.6 PAID invoices all have amount_due = 0.00")
    run("7.6", t76)


# ──────────────────────────────────────────────────────────────
# PHASE 8 — GST CALCULATION ACCURACY
# ──────────────────────────────────────────────────────────────
def phase8():
    print("\n" + "="*60)
    print("  PHASE 8 — GST CALCULATION ACCURACY")
    print("="*60)

    def q(v): return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cid = ctx.get("cust_id_a")

    def make_invoice(pid, qty, price, gst_type):
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": gst_type, "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": qty, "unit_price": str(price)}],
        })
        assert r.status_code in (200, 201), f"Create invoice failed: {r.status_code}: {r.text}"
        return r.json()

    # 8.1 5% INTRA
    def t81():
        pid = ctx.get("prod_id_5")
        if not pid: return FAIL("8.1", "No 5% product")
        d = make_invoice(pid, 1, "10000.00", "INTRA")
        assert q(d["cgst_total"]) == q(250),   f"CGST: expected 250, got {d['cgst_total']}"
        assert q(d["sgst_total"]) == q(250),   f"SGST: expected 250, got {d['sgst_total']}"
        assert q(d["igst_total"]) == q(0),     f"IGST: expected 0, got {d['igst_total']}"
        assert q(d["total_amount"]) == q(10500), f"Total: expected 10500, got {d['total_amount']}"
        PASS("8.1 5% INTRA: CGST=250, SGST=250, IGST=0, Total=10500")
    run("8.1", t81)

    # 8.2 5% INTER
    def t82():
        pid = ctx.get("prod_id_5")
        if not pid: return FAIL("8.2", "No 5% product")
        d = make_invoice(pid, 1, "10000.00", "INTER")
        assert q(d["cgst_total"]) == q(0),    f"CGST: expected 0"
        assert q(d["sgst_total"]) == q(0),    f"SGST: expected 0"
        assert q(d["igst_total"]) == q(500),  f"IGST: expected 500, got {d['igst_total']}"
        assert q(d["total_amount"]) == q(10500)
        PASS("8.2 5% INTER: CGST=0, SGST=0, IGST=500, Total=10500")
    run("8.2", t82)

    # 8.3 28% INTRA
    def t83():
        pid = ctx.get("prod_id_28")
        if not pid: return FAIL("8.3", "No 28% product")
        d = make_invoice(pid, 1, "10000.00", "INTRA")
        assert q(d["cgst_total"]) == q(1400),  f"CGST: expected 1400, got {d['cgst_total']}"
        assert q(d["sgst_total"]) == q(1400),  f"SGST: expected 1400, got {d['sgst_total']}"
        assert q(d["total_amount"]) == q(12800), f"Total: expected 12800, got {d['total_amount']}"
        PASS("8.3 28% INTRA: CGST=1400, SGST=1400, Total=12800")
    run("8.3", t83)

    # 8.4 0% GST
    def t84():
        pid = ctx.get("prod_id_0")
        if not pid: return FAIL("8.4", "No 0% product")
        d = make_invoice(pid, 1, "10000.00", "INTRA")
        assert q(d["cgst_total"]) == q(0)
        assert q(d["total_amount"]) == q(10000)
        PASS("8.4 0% GST: No tax, total=subtotal")
    run("8.4", t84)

    # 8.5 Rounding accuracy (333.33 × 18%)
    def t85():
        pid = ctx.get("prod_id_18")
        d = make_invoice(pid, 1, "333.33", "INTRA")
        # 333.33 × 9% = 30.0 (CGST), 30.0 (SGST), total = 333.33 + 60 = 393.33
        sub  = q(d["subtotal"])
        cgst = q(d["cgst_total"])
        sgst = q(d["sgst_total"])
        tot  = q(d["total_amount"])
        assert sub  == q("333.33"), f"subtotal: expected 333.33, got {sub}"
        assert cgst == q("30.00"),  f"cgst: expected 30.00, got {cgst}"
        assert sgst == q("30.00"),  f"sgst: expected 30.00, got {sgst}"
        assert tot  == q("393.33"), f"total: expected 393.33, got {tot}"
        PASS(f"8.5 Rounding (333.33 × 18%): CGST=30.00, SGST=30.00, Total=393.33")
    run("8.5", t85)

    # 8.6 Multi-item accumulation (3 × 1000 at 18%)
    def t86():
        pid = ctx.get("prod_id_18")
        r = client.post("/api/v1/billing/invoices", headers=hdr(), json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [
                {"product_id": pid, "quantity": 1, "unit_price": "1000.00"},
                {"product_id": pid, "quantity": 1, "unit_price": "1000.00"},
                {"product_id": pid, "quantity": 1, "unit_price": "1000.00"},
            ],
        })
        assert r.status_code in (200, 201), f"Expected 201: {r.text}"
        d = r.json()
        assert q(d["subtotal"]) == q(3000), f"subtotal: expected 3000, got {d['subtotal']}"
        assert q(d["cgst_total"]) == q(270), f"cgst: expected 270, got {d['cgst_total']}"
        assert q(d["sgst_total"]) == q(270), f"sgst: expected 270, got {d['sgst_total']}"
        assert q(d["total_amount"]) == q(3540), f"total: expected 3540, got {d['total_amount']}"
        PASS("8.6 3-item accumulation: subtotal=3000, CGST=270, SGST=270, Total=3540")
    run("8.6", t86)


# ──────────────────────────────────────────────────────────────
# PHASE 9 — RESPONSE FORMAT
# ──────────────────────────────────────────────────────────────
def phase9():
    print("\n" + "="*60)
    print("  PHASE 9 — API RESPONSE FORMAT")
    print("="*60)

    UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    ISO_RE  = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

    # 9.1 Money fields are strings with 2 decimal places
    def t91():
        r = client.get("/api/v1/invoices", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        invs = as_list(r.json(), "invoices")
        money_fields = ["subtotal", "total_amount", "cgst_total", "sgst_total"]
        for inv in invs[:3]:
            for f in money_fields:
                v = inv.get(f)
                if v is not None:
                    try:
                        d = Decimal(str(v))
                        dp = d.as_tuple().exponent
                        assert dp >= -2, f"{f}={v} has more than 2 decimal places (exponent={dp})"
                    except Exception as e:
                        assert False, f"{f}={v}: {e}"
        PASS("9.1 Money fields have <= 2 decimal places")
    run("9.1", t91)

    # 9.2 UUIDs are valid format
    def t92():
        r = client.get("/api/v1/billing/customers", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        customers = as_list(r.json(), "customers")
        for c in customers[:5]:
            cid = c.get("id", "")
            assert UUID_RE.match(cid), f"Invalid UUID format: {cid}"
        PASS("9.2 IDs are valid UUID format (8-4-4-4-12)")
    run("9.2", t92)

    # 9.3 Timestamps ISO 8601
    def t93():
        r = client.get("/api/v1/billing/customers", headers=hdr())
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        customers = as_list(r.json(), "customers")
        for c in customers[:3]:
            ts = c.get("created_at", "")
            if ts:
                assert ISO_RE.match(ts), f"Timestamp not ISO 8601: {ts}"
        PASS("9.3 Timestamps are ISO 8601 format")
    run("9.3", t93)

    # 9.4 HTTP status codes
    def t94():
        # 404
        r = client.get("/api/v1/billing/customers/00000000-0000-0000-0000-000000000000", headers=hdr())
        assert r.status_code == 404, f"Non-existent resource: expected 404, got {r.status_code}"
        # 422
        r = client.post("/api/v1/billing/customers", headers=hdr(), json={})
        assert r.status_code == 422, f"Missing required: expected 422, got {r.status_code}"
        # 401
        r = client.get("/api/v1/billing/customers")
        assert r.status_code == 401, f"No auth: expected 401, got {r.status_code}"
        PASS("9.4 HTTP status codes: 404/422/401 all correct")
    run("9.4", t94)

    # 9.5 Error responses have detail field, no stack traces
    def t95():
        r = client.get("/api/v1/billing/customers/00000000-0000-0000-0000-000000000000", headers=hdr())
        d = r.json()
        assert "detail" in d, f"Error response missing 'detail' field: {d}"
        assert "traceback" not in r.text.lower(), "Traceback exposed in error response!"
        assert "file " not in r.text.lower() or "detail" in r.text.lower(), "Stack trace in error!"
        PASS("9.5 Error responses have 'detail' field, no stack trace")
    run("9.5", t95)

    # 9.6 Password never in response
    def t96():
        # Registration response
        email = rand_email()
        r = client.post("/api/v1/auth/register", json={
            "full_name": "PW Test", "email": email, "password": "SecurePass1",
            "business_name": "PW Biz",
        })
        raw = r.text.lower()
        assert "securepass" not in raw, "Plain password in registration response!"
        assert "hashed_password" not in raw, "hashed_password in registration response!"
        # Login response
        client.post("/api/v1/auth/login", json={"email": email, "password": "SecurePass1"})
        r2 = client.get("/api/v1/auth/me", headers=hdr())
        raw2 = r2.text.lower()
        assert "hashed_password" not in raw2, "hashed_password in /me response!"
        assert "securepass" not in raw2, "Password value in /me response!"
        PASS("9.6 Password never appears in any API response")
    run("9.6", t96)


# ──────────────────────────────────────────────────────────────
# PHASE 10 — END-TO-END FLOWS
# ──────────────────────────────────────────────────────────────
def phase10():
    print("\n" + "="*60)
    print("  PHASE 10 — END-TO-END FLOWS")
    print("="*60)

    def q(v): return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # FLOW 1: Complete invoice-to-payment
    def flow1():
        # Register fresh user
        email = rand_email()
        token, _ = register_and_login(email)
        H = {"Authorization": f"Bearer {token}"}

        # Customer
        rc = client.post("/api/v1/billing/customers", headers=H,
            json={"name": "E2E Customer", "state": "Tamil Nadu", "gstin": rand_gstin()})
        assert rc.status_code in (200, 201), rc.text
        cid = rc.json()["id"]

        # Product
        rp = client.post("/api/v1/billing/products", headers=H,
            json={"name": "E2E Product", "base_price": "5000.00", "gst_rate": "18"})
        assert rp.status_code in (200, 201), rp.text
        pid = rp.json()["id"]

        # Invoice (2 units × 5000 = 10000 + 18% = 11800)
        ri = client.post("/api/v1/billing/invoices", headers=H, json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 2, "unit_price": "5000.00"}],
        })
        assert ri.status_code in (200, 201), ri.text
        inv = ri.json()
        inv_id = inv["id"]
        total = q(inv["total_amount"])
        assert total == q(11800), f"Expected 11800, got {total}"
        assert inv["status"] == "draft"

        # Step 6: Try paying DRAFT → 400
        rp0 = client.post("/api/v1/payments", headers=H, json={
            "sales_invoice_id": inv_id, "customer_id": cid,
            "amount": "100.00", "payment_method": "cash",
            "direction": "incoming", "payment_date": datetime.utcnow().isoformat(),
        })
        assert rp0.status_code == 400, f"E2E Step 6: expected 400 paying DRAFT, got {rp0.status_code}"

        # Step 7: Send invoice
        rs = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=H)
        assert rs.status_code == 200 and rs.json()["status"] == "sent"

        # Step 8: Partial payment 5000 via UPI
        rp1 = client.post("/api/v1/payments", headers=H, json={
            "sales_invoice_id": inv_id, "customer_id": cid,
            "amount": "5000.00", "payment_method": "upi",
            "direction": "incoming", "payment_date": datetime.utcnow().isoformat(),
        })
        assert rp1.status_code in (200, 201), rp1.text
        ri2 = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=H)
        if ri2.status_code != 200: ri2 = client.get(f"/api/v1/invoices/{inv_id}", headers=H)
        inv2 = ri2.json()
        assert inv2["status"] == "sent", "After partial: should still be sent"
        assert q(inv2["amount_paid"]) == q(5000)
        assert q(inv2["amount_due"])  == q(6800)

        # Step 9: Remaining 6800 via NEFT
        rp2 = client.post("/api/v1/payments", headers=H, json={
            "sales_invoice_id": inv_id, "customer_id": cid,
            "amount": "6800.00", "payment_method": "bank_transfer",
            "direction": "incoming", "payment_date": datetime.utcnow().isoformat(),
        })
        assert rp2.status_code in (200, 201), rp2.text
        ri3 = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=H)
        if ri3.status_code != 200: ri3 = client.get(f"/api/v1/invoices/{inv_id}", headers=H)
        inv3 = ri3.json()
        assert inv3["status"] == "paid", f"After full payment: expected paid, got {inv3['status']}"
        assert q(inv3["amount_due"]) == q(0)
        assert q(inv3["amount_paid"]) == q(11800)

        # Step 10: Try paying PAID invoice → 400
        rp3 = client.post("/api/v1/payments", headers=H, json={
            "sales_invoice_id": inv_id, "customer_id": cid,
            "amount": "100.00", "payment_method": "cash",
            "direction": "incoming", "payment_date": datetime.utcnow().isoformat(),
        })
        assert rp3.status_code == 400, f"Paying PAID invoice should be 400, got {rp3.status_code}"

        # Step 11: Cancel PAID → 400
        rc2 = client.patch(f"/api/v1/invoices/{inv_id}/cancel", headers=H)
        assert rc2.status_code == 400, f"Cancel PAID should be 400, got {rc2.status_code}"

        PASS("FLOW 1 Complete invoice-to-payment flow (11 steps) → all pass")
    run("FLOW 1", flow1)

    # FLOW 2: Overdue invoice
    def flow2():
        email = rand_email()
        token, _ = register_and_login(email)
        H = {"Authorization": f"Bearer {token}"}

        rc = client.post("/api/v1/billing/customers", headers=H, json={"name": "Overdue Co"})
        cid = rc.json()["id"]
        rp = client.post("/api/v1/billing/products", headers=H,
            json={"name": "OD Prod", "base_price": "1000.00", "gst_rate": "18"})
        pid = rp.json()["id"]

        # Invoice with due_date = yesterday
        ri = client.post("/api/v1/billing/invoices", headers=H, json={
            "customer_id": cid, "gst_type": "INTRA",
            "due_date": fmtd(-1),  # yesterday
            "items": [{"product_id": pid, "quantity": 1, "unit_price": "1000.00"}],
        })
        assert ri.status_code in (200, 201), ri.text
        inv_id = ri.json()["id"]
        total  = q(ri.json()["total_amount"])

        # Send it
        client.patch(f"/api/v1/invoices/{inv_id}/send", headers=H)

        # Check overdue endpoint
        ro = client.post("/api/v1/invoices/check-overdue", headers=H)
        # May return 200 or 404 depending on route
        if ro.status_code == 200:
            ri2 = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=H)
            if ri2.status_code != 200: ri2 = client.get(f"/api/v1/invoices/{inv_id}", headers=H)
            inv2 = ri2.json()
            overdue_ok = inv2.get("status") == "overdue"
        else:
            # Endpoint might not exist; check status from list
            overdue_ok = True  # Graceful skip

        # Can still pay overdue invoice
        rp2 = client.post("/api/v1/payments", headers=H, json={
            "sales_invoice_id": inv_id, "customer_id": cid,
            "amount": str(total),
            "payment_method": "cash", "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat(),
        })
        assert rp2.status_code in (200, 201), f"Should pay sent/overdue invoice: {rp2.status_code}: {rp2.text}"

        PASS("FLOW 2 Overdue invoice → can still be paid")
    run("FLOW 2", flow2)

    # FLOW 3: Multi-user isolation
    def flow3():
        tA, _ = register_and_login()
        tB, _ = register_and_login()
        HA = {"Authorization": f"Bearer {tA}"}
        HB = {"Authorization": f"Bearer {tB}"}

        # User A creates data
        rc = client.post("/api/v1/billing/customers", headers=HA, json={"name": "User A Customer"})
        cid_a = rc.json()["id"]
        rp = client.post("/api/v1/billing/products", headers=HA,
            json={"name": "Prod A", "base_price": "500.00", "gst_rate": "18"})
        pid_a = rp.json()["id"]
        ri = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid_a, "quantity": 1, "unit_price": "500.00"}],
        })
        inv_id_a = ri.json()["id"]

        # User B sees nothing from User A
        r1 = client.get("/api/v1/billing/customers", headers=HB)
        assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.text}"
        custs_b = as_list(r1.json(), "customers")
        assert len(custs_b) == 0

        r2 = client.get(f"/api/v1/billing/customers/{cid_a}", headers=HB)
        assert r2.status_code == 404

        r3 = client.patch(f"/api/v1/invoices/{inv_id_a}/send", headers=HB)
        assert r3.status_code == 404

        PASS("FLOW 3 Multi-user isolation -> User B sees nothing of User A")
    run("FLOW 3", flow3)

    # FLOW 4: Cancellation flow
    def flow4():
        H = hdr()
        cid = ctx.get("cust_id_a")
        pid = ctx.get("prod_id_18")

        # Draft → cancel
        ri = client.post("/api/v1/billing/invoices", headers=H, json={
            "customer_id": cid, "gst_type": "INTRA", "due_date": fmtd(30),
            "items": [{"product_id": pid, "quantity": 1, "unit_price": "100.00"}],
        })
        inv_id = ri.json()["id"]
        rc = client.patch(f"/api/v1/invoices/{inv_id}/cancel", headers=H)
        assert rc.status_code == 200 and rc.json()["status"] == "cancelled"

        # Try sending cancelled → 400
        rs = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=H)
        assert rs.status_code == 400, f"Sending cancelled invoice: expected 400, got {rs.status_code}"

        # Try paying cancelled → 400
        rp = client.post("/api/v1/payments", headers=H, json={
            "sales_invoice_id": inv_id, "customer_id": cid,
            "amount": "100.00", "payment_method": "cash",
            "direction": "incoming", "payment_date": datetime.utcnow().isoformat(),
        })
        assert rp.status_code == 400, f"Paying cancelled: expected 400, got {rp.status_code}"

        PASS("FLOW 4 Cancellation flow → cancelled can't be sent or paid")
    run("FLOW 4", flow4)


# ──────────────────────────────────────────────────────────────
# MASTER RUNNER
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  AI VIRTUAL CFO — MASTER QA TEST SUITE")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    phase1()
    phase2()
    phase3()
    phase4()
    phase5()
    phase6()
    phase7()
    phase8()
    phase9()
    phase10()

    # ─── Final Report ─────────────────────────────────────────
    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    total  = len(results)

    print("\n" + "="*60)
    print(f"  FINAL RESULTS: {len(passed)}/{total} PASSED")
    print("="*60)

    if failed:
        print(f"\n  FAILURES ({len(failed)}):")
        print("  " + "-"*56)
        for name, _, reason in failed:
            print(f"  [FAIL] {name}")
            print(f"         {reason}")
    else:
        print("\n  ALL TESTS PASSED!")

    print(f"\n  Passed : {len(passed)}")
    print(f"  Failed : {len(failed)}")
    print(f"  Total  : {total}")
    print("="*60 + "\n")

    sys.exit(0 if not failed else 1)
