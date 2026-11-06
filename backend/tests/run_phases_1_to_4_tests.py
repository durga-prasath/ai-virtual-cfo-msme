# backend/tests/run_phases_1_to_4_tests.py
"""
DEDICATED TEST SUITE: PHASES 1 TO 4
Systematic testing of:
  Phase 1 — Authentication (Blocks 1.1, 1.2, 1.3)
  Phase 2 — Customers (Blocks 2.1, 2.2)
  Phase 3 — Products (Block 3.1)
  Phase 4 — Invoices & Lifecycle (Blocks 4.1, 4.2)

Every test directly maps 1-to-1 with the user testing specification.
Run: python -W ignore tests/run_phases_1_to_4_tests.py
"""

import sys
import os
import re
import random
import string
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, date

sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from main import app
from app.db.database import SessionLocal
from app.models.user import User
from app.models.customer import Customer
from app.models.sales_invoice import SalesInvoice
from app.core.security import create_access_token

client = TestClient(app, raise_server_exceptions=False)

results = []
context = {}

def PASS(test_id, name):
    msg = f"  [PASS] {test_id} - {name}\n"
    sys.stdout.buffer.write(msg.encode("utf-8"))
    sys.stdout.buffer.flush()
    results.append((test_id, True, None))

def FAIL(test_id, name, reason):
    msg = f"  [FAIL] {test_id} - {name}\n         => {reason}\n"
    sys.stdout.buffer.write(msg.encode("utf-8"))
    sys.stdout.buffer.flush()
    results.append((test_id, False, reason))

def run_test(test_id, name, fn):
    try:
        fn()
    except AssertionError as e:
        FAIL(test_id, name, str(e))
    except Exception as e:
        FAIL(test_id, name, f"{type(e).__name__}: {e}")

# Helpers
def rand_email():
    return f"qa_{random.randint(100000, 999999)}@testcfo.com"

def rand_gstin(state_code="33"):
    letters = ''.join(random.choices(string.ascii_uppercase, k=5))
    digits  = ''.join(random.choices(string.digits, k=4))
    alpha   = random.choice(string.ascii_uppercase)
    extra   = random.choice('123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    check   = random.choice(string.digits + string.ascii_uppercase)
    return f"{state_code}{letters}{digits}{alpha}{extra}Z{check}"

def get_auth_header(token):
    return {"Authorization": f"Bearer {token}"}

def q(val):
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def as_list(res_data, *keys):
    if isinstance(res_data, list):
        return res_data
    for k in keys:
        if isinstance(res_data, dict) and k in res_data:
            return res_data[k]
    return []

# ═══════════════════════════════════════════════════════════════
# PHASE 1 — AUTHENTICATION TESTING
# ═══════════════════════════════════════════════════════════════
def test_phase_1():
    print("\n" + "="*65)
    print("  PHASE 1 -- AUTHENTICATION TESTING")
    print("="*65)

    # ── TEST BLOCK 1.1: USER REGISTRATION ────────────────────────
    print("\n  -- BLOCK 1.1: USER REGISTRATION --")

    # 1.1.1 Valid registration (Happy Path)
    def t1_1_1():
        email = rand_email()
        pwd = "SecurePass1"
        valid_gstin = rand_gstin()
        r = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": pwd,
            "full_name": "Test Owner",
            "phone": "9876543210",
            "business_name": "Test Business Pvt Ltd",
            "gstin": valid_gstin
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        context["user_a_email"] = email
        context["user_a_pwd"] = pwd
        context["user_a_id"] = data.get("id")

        assert "id" in data, "Response missing 'id'"
        assert data["email"] == email, "Response email mismatch"
        assert data["full_name"] == "Test Owner", "Response full_name mismatch"
        assert str(data.get("role", "")).upper() == "OWNER", f"Expected role='OWNER', got {data.get('role')}"
        assert data["is_active"] is True, "is_active should be True"
        assert data["is_verified"] is False, "is_verified should be False"
        assert "hashed_password" not in data, "hashed_password leaked in response"
        assert pwd not in r.text, "Plain text password leaked in response"

        # Check DB directly
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            assert user is not None, "User not found in PostgreSQL"
            assert user.hashed_password.startswith("$2b$") or user.hashed_password.startswith("$2a$"), \
                f"Password hash not in bcrypt format: {user.hashed_password[:10]}"
            assert user.hashed_password != pwd, "Password stored as plaintext in DB"
        finally:
            db.close()

        PASS("1.1.1", "Valid registration (Happy Path) -> 201 Created & DB verified")
    run_test("1.1.1", "Valid registration", t1_1_1)

    # 1.1.2 Duplicate email rejection
    def t1_1_2():
        r = client.post("/api/v1/auth/register", json={
            "email": context["user_a_email"],
            "password": "SecurePass1",
            "full_name": "Duplicate User",
            "business_name": "Dupe Biz"
        })
        assert r.status_code in (400, 409), f"Expected 409/400 Conflict, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "").lower()
        assert "already" in detail or "exist" in detail, f"Detail should mention already exists: {detail}"
        PASS("1.1.2", "Duplicate email rejection -> 409 Conflict")
    run_test("1.1.2", "Duplicate email rejection", t1_1_2)

    # 1.1.3 Invalid email format
    def t1_1_3():
        r = client.post("/api/v1/auth/register", json={
            "email": "notanemail",
            "password": "SecurePass1",
            "full_name": "Bad Email",
            "business_name": "Bad Email Biz"
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("1.1.3", "Invalid email format -> 422 Unprocessable Entity")
    run_test("1.1.3", "Invalid email format", t1_1_3)

    # 1.1.4 Weak password (no digit)
    def t1_1_4():
        r = client.post("/api/v1/auth/register", json={
            "email": rand_email(),
            "password": "NoDigitsHere",
            "full_name": "No Digit",
            "business_name": "No Digit Biz"
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        detail = str(r.json()).lower()
        assert "digit" in detail, f"Error should mention digit requirement: {detail}"
        PASS("1.1.4", "Weak password (no digit) -> 422 Unprocessable Entity")
    run_test("1.1.4", "Weak password (no digit)", t1_1_4)

    # 1.1.5 Weak password (no uppercase)
    def t1_1_5():
        r = client.post("/api/v1/auth/register", json={
            "email": rand_email(),
            "password": "alllowercase1",
            "full_name": "No Upper",
            "business_name": "No Upper Biz"
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        detail = str(r.json()).lower()
        assert "uppercase" in detail, f"Error should mention uppercase requirement: {detail}"
        PASS("1.1.5", "Weak password (no uppercase) -> 422 Unprocessable Entity")
    run_test("1.1.5", "Weak password (no uppercase)", t1_1_5)

    # 1.1.6 Password too short
    def t1_1_6():
        r = client.post("/api/v1/auth/register", json={
            "email": rand_email(),
            "password": "Ab1",
            "full_name": "Short Pwd",
            "business_name": "Short Pwd Biz"
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("1.1.6", "Password too short -> 422 Unprocessable Entity")
    run_test("1.1.6", "Password too short", t1_1_6)

    # 1.1.7 Missing required fields
    def t1_1_7():
        r = client.post("/api/v1/auth/register", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("1.1.7", "Missing required fields -> 422 Unprocessable Entity")
    run_test("1.1.7", "Missing required fields", t1_1_7)

    # 1.1.8 Invalid GSTIN format
    def t1_1_8():
        r = client.post("/api/v1/auth/register", json={
            "email": rand_email(),
            "password": "SecurePass1",
            "full_name": "Bad GSTIN",
            "business_name": "Bad GSTIN Biz",
            "gstin": "INVALID123"
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("1.1.8", "Invalid GSTIN format -> 422 Unprocessable Entity")
    run_test("1.1.8", "Invalid GSTIN format", t1_1_8)

    # 1.1.9 Valid GSTIN format
    def t1_1_9():
        valid_gstin = rand_gstin("33")
        email = rand_email()
        r = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "SecurePass1",
            "full_name": "Valid GSTIN User",
            "business_name": "GSTIN Biz",
            "gstin": valid_gstin
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("gstin") == valid_gstin, f"Expected {valid_gstin}, got {data.get('gstin')}"
        PASS("1.1.9", "Valid GSTIN format -> 201 Created, GSTIN saved correctly")
    run_test("1.1.9", "Valid GSTIN format", t1_1_9)


    # ── TEST BLOCK 1.2: USER LOGIN ───────────────────────────────
    print("\n  -- BLOCK 1.2: USER LOGIN --")

    # 1.2.1 Valid login (Happy Path)
    def t1_2_1():
        r = client.post("/api/v1/auth/login", json={
            "email": context["user_a_email"],
            "password": context["user_a_pwd"]
        })
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "access_token" in data, "Response missing access_token"
        assert data.get("token_type") == "bearer", f"Expected 'bearer', got {data.get('token_type')}"
        parts = data["access_token"].split(".")
        assert len(parts) == 3, f"JWT must consist of 3 parts separated by dots, got {len(parts)}"
        context["token_a"] = data["access_token"]
        PASS("1.2.1", "Valid login (Happy Path) -> 200 OK, valid 3-part JWT")
    run_test("1.2.1", "Valid login", t1_2_1)

    # 1.2.2 Wrong password
    def t1_2_2():
        r = client.post("/api/v1/auth/login", json={
            "email": context["user_a_email"],
            "password": "WrongPass1"
        })
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "invalid" in detail.lower() or "incorrect" in detail.lower(), f"Unexpected message: {detail}"
        context["generic_auth_err"] = detail
        PASS("1.2.2", "Wrong password -> 401 Unauthorized (generic error message)")
    run_test("1.2.2", "Wrong password", t1_2_2)

    # 1.2.3 Non-existent email
    def t1_2_3():
        r = client.post("/api/v1/auth/login", json={
            "email": "nobody@nowhere.com",
            "password": "SecurePass1"
        })
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        # Security: must NOT reveal whether email exists
        assert detail == context.get("generic_auth_err", detail), "Error message should match wrong password message"
        PASS("1.2.3", "Non-existent email -> 401 Unauthorized (same message as wrong password)")
    run_test("1.2.3", "Non-existent email", t1_2_3)

    # 1.2.4 Empty credentials
    def t1_2_4():
        r = client.post("/api/v1/auth/login", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("1.2.4", "Empty credentials -> 422 Unprocessable Entity")
    run_test("1.2.4", "Empty credentials", t1_2_4)

    # 1.2.5 SQL injection attempt
    def t1_2_5():
        r = client.post("/api/v1/auth/login", json={
            "email": "' OR '1'='1",
            "password": "password"
        })
        assert r.status_code in (401, 422), f"SQL injection returned unexpected {r.status_code}"
        assert "syntax error" not in r.text.lower() and "traceback" not in r.text.lower(), \
            "Database error exposed in response!"
        PASS("1.2.5", "SQL injection attempt -> 401/422, no database errors exposed")
    run_test("1.2.5", "SQL injection attempt", t1_2_5)


    # ── TEST BLOCK 1.3: JWT TOKEN VALIDATION ─────────────────────
    print("\n  -- BLOCK 1.3: JWT TOKEN VALIDATION --")

    # 1.3.1 Access protected route with valid token
    def t1_3_1():
        r = client.get("/api/v1/auth/me", headers=get_auth_header(context["token_a"]))
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["email"] == context["user_a_email"], "Wrong user data returned"
        assert "hashed_password" not in data, "Password hash exposed in /me"
        PASS("1.3.1", "Access protected route with valid token -> 200 OK with user profile")
    run_test("1.3.1", "Protected route with valid token", t1_3_1)

    # 1.3.2 Access protected route without token
    def t1_3_2():
        r = client.get("/api/v1/auth/me")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        PASS("1.3.2", "Access protected route without token -> 401/403 Unauthorized")
    run_test("1.3.2", "Protected route without token", t1_3_2)

    # 1.3.3 Access with malformed token
    def t1_3_3():
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtokenstring"})
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        PASS("1.3.3", "Access with malformed token -> 401 Unauthorized")
    run_test("1.3.3", "Malformed token", t1_3_3)

    # 1.3.4 Access with tampered token
    def t1_3_4():
        tok = context["token_a"]
        parts = tok.split(".")
        # Modify signature
        tampered = f"{parts[0]}.{parts[1]}.{'A' * len(parts[2])}"
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        PASS("1.3.4", "Access with tampered token -> 401 Unauthorized (signature verification working)")
    run_test("1.3.4", "Tampered token", t1_3_4)

    # 1.3.5 Access with expired token
    def t1_3_5():
        expired_token = create_access_token(
            subject=str(context["user_a_id"]),
            expires_delta=timedelta(minutes=-10)
        )
        r = client.get("/api/v1/auth/me", headers=get_auth_header(expired_token))
        assert r.status_code in (401, 403), f"Expected 401 for expired token, got {r.status_code}"
        PASS("1.3.5", "Access with expired token -> 401 Unauthorized")
    run_test("1.3.5", "Expired token", t1_3_5)

    # 1.3.6 Token without Bearer prefix
    def t1_3_6():
        r = client.get("/api/v1/auth/me", headers={"Authorization": context["token_a"]})
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        PASS("1.3.6", "Token without Bearer prefix -> 401/403 rejected")
    run_test("1.3.6", "Token without Bearer prefix", t1_3_6)

    # 1.3.7 GET /me returns correct user
    def t1_3_7():
        # Register User B
        email_b = rand_email()
        client.post("/api/v1/auth/register", json={
            "email": email_b,
            "password": "SecurePass2",
            "full_name": "User B",
            "business_name": "User B Enterprises"
        })
        r_login_b = client.post("/api/v1/auth/login", json={"email": email_b, "password": "SecurePass2"})
        token_b = r_login_b.json()["access_token"]
        context["token_b"] = token_b
        context["user_b_email"] = email_b

        # Check /me with User A's token
        r_a = client.get("/api/v1/auth/me", headers=get_auth_header(context["token_a"]))
        assert r_a.json()["email"] == context["user_a_email"], "User A did not get User A data"

        # Check /me with User B's token
        r_b = client.get("/api/v1/auth/me", headers=get_auth_header(context["token_b"]))
        assert r_b.json()["email"] == email_b, "User B did not get User B data"
        assert r_a.json()["id"] != r_b.json()["id"], "User A and B have matching IDs"

        PASS("1.3.7", "GET /me returns correct user data per token")
    run_test("1.3.7", "GET /me user isolation", t1_3_7)


# ═══════════════════════════════════════════════════════════════
# PHASE 2 — CUSTOMER TESTING
# ═══════════════════════════════════════════════════════════════
def test_phase_2():
    print("\n" + "="*65)
    print("  PHASE 2 -- CUSTOMER TESTING")
    print("="*65)

    HA = get_auth_header(context["token_a"])
    HB = get_auth_header(context["token_b"])

    # ── TEST BLOCK 2.1: CREATE CUSTOMER ──────────────────────────
    print("\n  -- BLOCK 2.1: CREATE CUSTOMER --")

    # 2.1.1 Valid customer creation (Happy Path)
    def t2_1_1():
        cust_gstin = rand_gstin("33")
        cust_email = f"ravi_{random.randint(10000, 99999)}@example.com"
        r = client.post("/api/v1/billing/customers", headers=HA, json={
            "name": "Ravi Enterprises",
            "email": cust_email,
            "phone": "9876543210",
            "gstin": cust_gstin,
            "address": "123 Anna Salai",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600001"
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        context["cust_a_id"] = data.get("id")
        context["cust_a_gstin"] = cust_gstin

        assert "id" in data, "Customer response missing 'id'"
        assert re.match(r"^[0-9a-f-]{36}$", data["id"]), "Customer id is not a valid UUID"
        assert data.get("user_id") == context["user_a_id"], "Customer user_id does not match logged in user"
        assert data.get("gstin") == cust_gstin.upper(), "GSTIN not saved in uppercase"

        # Check DB
        db = SessionLocal()
        try:
            c = db.query(Customer).filter(Customer.id == data["id"]).first()
            assert c is not None, "Customer not found in DB by ID"
            assert c.email == cust_email, "DB email mismatch"
            assert str(c.user_id) == str(context["user_a_id"]), "DB user_id mismatch"
        finally:
            db.close()

        PASS("2.1.1", "Valid customer creation (Happy Path) -> 201 Created & DB verified")
    run_test("2.1.1", "Valid customer creation", t2_1_1)

    # 2.1.2 Customer without optional fields
    def t2_1_2():
        r = client.post("/api/v1/billing/customers", headers=HA, json={"name": "Minimal Customer"})
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("name") == "Minimal Customer"
        assert data.get("email") is None
        assert data.get("phone") is None
        assert data.get("gstin") is None
        PASS("2.1.2", "Customer without optional fields -> 201 Created with null fields")
    run_test("2.1.2", "Customer without optional fields", t2_1_2)

    # 2.1.3 user_id in body is ignored
    def t2_1_3():
        fake_id = "00000000-0000-0000-0000-000000000000"
        r = client.post("/api/v1/billing/customers", headers=HA, json={
            "name": "Injection Test",
            "user_id": fake_id
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("user_id") == context["user_a_id"], "Server accepted client injected user_id!"
        assert data.get("user_id") != fake_id, "Injected user_id persisted in DB"
        PASS("2.1.3", "user_id in body is ignored -> Server overrides from JWT")
    run_test("2.1.3", "user_id in body is ignored", t2_1_3)

    # 2.1.4 Invalid GSTIN format
    def t2_1_4():
        r = client.post("/api/v1/billing/customers", headers=HA, json={
            "name": "Bad GSTIN Customer",
            "gstin": "BADGSTIN123"
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("2.1.4", "Invalid GSTIN format -> 422 Unprocessable Entity")
    run_test("2.1.4", "Invalid GSTIN format", t2_1_4)

    # 2.1.5 Duplicate GSTIN for same user
    def t2_1_5():
        r = client.post("/api/v1/billing/customers", headers=HA, json={
            "name": "Another Customer Same GSTIN",
            "gstin": context["cust_a_gstin"]
        })
        assert r.status_code == 409, f"Expected 409 Conflict, got {r.status_code}: {r.text}"
        PASS("2.1.5", "Duplicate GSTIN for same user -> 409 Conflict")
    run_test("2.1.5", "Duplicate GSTIN for same user", t2_1_5)

    # 2.1.6 Missing required name field
    def t2_1_6():
        r = client.post("/api/v1/billing/customers", headers=HA, json={"email": "test@test.com"})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("2.1.6", "Missing required name field -> 422 Unprocessable Entity")
    run_test("2.1.6", "Missing required name field", t2_1_6)

    # 2.1.7 Name too short
    def t2_1_7():
        r = client.post("/api/v1/billing/customers", headers=HA, json={"name": ""})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("2.1.7", "Name too short (empty string) -> 422 Unprocessable Entity")
    run_test("2.1.7", "Name too short", t2_1_7)


    # ── TEST BLOCK 2.2: LIST & GET CUSTOMERS ─────────────────────
    print("\n  -- BLOCK 2.2: LIST & GET CUSTOMERS --")

    # 2.2.1 List customers
    def t2_2_1():
        r = client.get("/api/v1/billing/customers", headers=HA)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        customers = as_list(r.json(), "customers")
        assert len(customers) >= 1, "Expected at least 1 customer for User A"
        for c in customers:
            assert c.get("user_id") == context["user_a_id"], "Customer belonging to another user returned"
        PASS("2.2.1", "List customers -> 200 OK with User A's customers only")
    run_test("2.2.1", "List customers", t2_2_1)

    # 2.2.2 List customers as different user
    def t2_2_2():
        r = client.get("/api/v1/billing/customers", headers=HB)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        customers = as_list(r.json(), "customers")
        assert len(customers) == 0, f"User B should see 0 customers, got {len(customers)}"
        PASS("2.2.2", "List customers as different user -> Empty array [] (Data Isolation OK)")
    run_test("2.2.2", "List customers as different user", t2_2_2)

    # 2.2.3 Get customer by ID
    def t2_2_3():
        cid = context["cust_a_id"]
        r = client.get(f"/api/v1/billing/customers/{cid}", headers=HA)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["id"] == cid
        assert data["name"] == "Ravi Enterprises"
        PASS("2.2.3", "Get customer by ID -> 200 OK with correct customer data")
    run_test("2.2.3", "Get customer by ID", t2_2_3)

    # 2.2.4 Get customer belonging to another user
    def t2_2_4():
        cid = context["cust_a_id"]
        r = client.get(f"/api/v1/billing/customers/{cid}", headers=HB)
        assert r.status_code == 404, f"Expected 404 for other user's customer, got {r.status_code}"
        PASS("2.2.4", "Get customer belonging to another user -> 404 Not Found")
    run_test("2.2.4", "Get other user customer", t2_2_4)

    # 2.2.5 Get non-existent customer
    def t2_2_5():
        fake_cid = "00000000-0000-0000-0000-000000000000"
        r = client.get(f"/api/v1/billing/customers/{fake_cid}", headers=HA)
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        PASS("2.2.5", "Get non-existent customer -> 404 Not Found")
    run_test("2.2.5", "Get non-existent customer", t2_2_5)

    # 2.2.6 Pagination test
    def t2_2_6():
        # Create fresh user with 10 customers
        email_p = rand_email()
        client.post("/api/v1/auth/register", json={
            "email": email_p,
            "password": "SecurePass1",
            "full_name": "Pagination User",
            "business_name": "Pagination Inc"
        })
        tok_p = client.post("/api/v1/auth/login", json={"email": email_p, "password": "SecurePass1"}).json()["access_token"]
        HP = get_auth_header(tok_p)

        for i in range(10):
            client.post("/api/v1/billing/customers", headers=HP, json={"name": f"Page Customer {i:02d}"})

        r_page1 = client.get("/api/v1/billing/customers?skip=0&limit=5", headers=HP)
        list1 = as_list(r_page1.json(), "customers")
        assert len(list1) == 5, f"Page 1 expected 5 items, got {len(list1)}"

        r_page2 = client.get("/api/v1/billing/customers?skip=5&limit=5", headers=HP)
        list2 = as_list(r_page2.json(), "customers")
        assert len(list2) == 5, f"Page 2 expected 5 items, got {len(list2)}"

        ids1 = {c["id"] for c in list1}
        ids2 = {c["id"] for c in list2}
        assert ids1.isdisjoint(ids2), "Pages overlap: item exists in both page 1 and page 2"
        PASS("2.2.6", "Pagination test -> skip=0&limit=5 and skip=5&limit=5 return disjoint sets")
    run_test("2.2.6", "Pagination test", t2_2_6)


# ═══════════════════════════════════════════════════════════════
# PHASE 3 — PRODUCT TESTING
# ═══════════════════════════════════════════════════════════════
def test_phase_3():
    print("\n" + "="*65)
    print("  PHASE 3 -- PRODUCT TESTING")
    print("="*65)

    HA = get_auth_header(context["token_a"])

    # ── TEST BLOCK 3.1: CREATE PRODUCT ───────────────────────────
    print("\n  -- BLOCK 3.1: CREATE PRODUCT --")

    # 3.1.1 Valid product (Happy Path)
    def t3_1_1():
        r = client.post("/api/v1/billing/products", headers=HA, json={
            "name": "Web Development Service",
            "description": "Custom web app development",
            "hsn_code": "998314",
            "base_price": "5000.00",
            "gst_rate": "18",
            "unit": "hour"
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        assert "id" in data, "Product missing 'id'"
        assert q(data["base_price"]) == q(5000.00), f"base_price mismatch: {data['base_price']}"
        assert q(data["gst_rate"]) == q(18.00), f"gst_rate mismatch: {data['gst_rate']}"
        context["prod_18_id"] = data["id"]
        PASS("3.1.1", "Valid product (Happy Path) -> 201 Created with Decimal base_price & gst_rate")
    run_test("3.1.1", "Valid product", t3_1_1)

    # 3.1.2 Valid GST rate slabs (0, 5, 12, 18, 28)
    def t3_1_2():
        slabs = [0, 5, 12, 18, 28]
        for rate in slabs:
            r = client.post("/api/v1/billing/products", headers=HA, json={
                "name": f"Product Slab {rate}%",
                "base_price": "1000.00",
                "gst_rate": str(rate)
            })
            assert r.status_code in (200, 201), f"Slab {rate}% failed with {r.status_code}: {r.text}"
            context[f"prod_{rate}_id"] = r.json()["id"]
        PASS("3.1.2", "Valid GST rate slabs (0, 5, 12, 18, 28) -> All 201 Created")
    run_test("3.1.2", "Valid GST rate slabs", t3_1_2)

    # 3.1.3 Invalid GST rate ("15")
    def t3_1_3():
        r = client.post("/api/v1/billing/products", headers=HA, json={
            "name": "Invalid Rate Product",
            "base_price": "1000.00",
            "gst_rate": "15"
        })
        assert r.status_code == 422, f"Expected 422 for 15% GST, got {r.status_code}: {r.text}"
        detail = str(r.json()).lower()
        assert "0" in detail and "28" in detail, f"Error should mention valid slabs: {detail}"
        PASS("3.1.3", "Invalid GST rate (15) -> 422 Unprocessable Entity (mentions valid slabs)")
    run_test("3.1.3", "Invalid GST rate", t3_1_3)

    # 3.1.4 Negative price
    def t3_1_4():
        r = client.post("/api/v1/billing/products", headers=HA, json={
            "name": "Negative Price Product",
            "base_price": "-100",
            "gst_rate": "18"
        })
        assert r.status_code == 422, f"Expected 422 for negative price, got {r.status_code}: {r.text}"
        PASS("3.1.4", "Negative price -> 422 Unprocessable Entity")
    run_test("3.1.4", "Negative price", t3_1_4)

    # 3.1.5 Zero price
    def t3_1_5():
        r = client.post("/api/v1/billing/products", headers=HA, json={
            "name": "Zero Price Product",
            "base_price": "0",
            "gst_rate": "18"
        })
        assert r.status_code == 422, f"Expected 422 for zero price, got {r.status_code}: {r.text}"
        PASS("3.1.5", "Zero price -> 422 Unprocessable Entity")
    run_test("3.1.5", "Zero price", t3_1_5)

    # 3.1.6 Decimal price precision ("999.99")
    def t3_1_6():
        r = client.post("/api/v1/billing/products", headers=HA, json={
            "name": "Decimal Precision Product",
            "base_price": "999.99",
            "gst_rate": "18"
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        assert q(r.json()["base_price"]) == q("999.99")
        PASS("3.1.6", "Decimal price precision (999.99) -> 201 Created and stored accurately")
    run_test("3.1.6", "Decimal price precision", t3_1_6)

    # 3.1.7 Missing base_price
    def t3_1_7():
        r = client.post("/api/v1/billing/products", headers=HA, json={
            "name": "Missing Price Product",
            "gst_rate": "18"
        })
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        PASS("3.1.7", "Missing base_price -> 422 Unprocessable Entity")
    run_test("3.1.7", "Missing base_price", t3_1_7)


# ═══════════════════════════════════════════════════════════════
# PHASE 4 — INVOICE TESTING
# ═══════════════════════════════════════════════════════════════
def test_phase_4():
    print("\n" + "="*65)
    print("  PHASE 4 -- INVOICE TESTING")
    print("="*65)

    HA = get_auth_header(context["token_a"])
    HB = get_auth_header(context["token_b"])
    cid_a = context["cust_a_id"]
    pid_18 = context["prod_18_id"]

    # ── TEST BLOCK 4.1: CREATE INVOICE ───────────────────────────
    print("\n  -- BLOCK 4.1: CREATE INVOICE --")

    # 4.1.1 Valid intra-state invoice (Happy Path)
    def t4_1_1():
        r = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "due_date": "2026-12-31",
            "items": [
                {
                    "product_id": pid_18,
                    "quantity": "10",
                    "unit_price": "1000.00"
                }
            ]
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        assert q(d["subtotal"]) == q("10000.00"), f"subtotal: {d['subtotal']}"
        assert q(d["cgst_total"]) == q("900.00"), f"cgst_total: {d['cgst_total']}"
        assert q(d["sgst_total"]) == q("900.00"), f"sgst_total: {d['sgst_total']}"
        assert q(d["igst_total"]) == q("0.00"), f"igst_total: {d['igst_total']}"
        assert q(d["tax_amount"]) == q("1800.00"), f"tax_amount: {d['tax_amount']}"
        assert q(d["total_amount"]) == q("11800.00"), f"total_amount: {d['total_amount']}"
        assert q(d["amount_due"]) == q("11800.00"), f"amount_due: {d['amount_due']}"
        assert q(d["amount_paid"]) == q("0.00"), f"amount_paid: {d['amount_paid']}"
        assert d["status"] == "draft", f"status: {d['status']}"
        assert d["invoice_number"].startswith("INV-"), f"invoice_number: {d['invoice_number']}"

        context["inv_draft_1"] = d["id"]
        PASS("4.1.1", "Valid intra-state invoice (Happy Path) -> Subtotal=10000, CGST=900, SGST=900, Total=11800")
    run_test("4.1.1", "Valid intra-state invoice", t4_1_1)

    # 4.1.2 Valid inter-state invoice
    def t4_1_2():
        r = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTER",
            "due_date": "2026-12-31",
            "items": [
                {
                    "product_id": pid_18,
                    "quantity": "10",
                    "unit_price": "1000.00"
                }
            ]
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        assert q(d["cgst_total"]) == q("0.00")
        assert q(d["sgst_total"]) == q("0.00")
        assert q(d["igst_total"]) == q("1800.00")
        assert q(d["total_amount"]) == q("11800.00")
        context["inv_inter_id"] = d["id"]
        PASS("4.1.2", "Valid inter-state invoice -> CGST=0, SGST=0, IGST=1800, Total=11800")
    run_test("4.1.2", "Valid inter-state invoice", t4_1_2)

    # 4.1.3 GST math verification (multiple items: 18% + 12%)
    def t4_1_3():
        pid_12 = context.get("prod_12_id")
        r = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "due_date": "2026-12-31",
            "items": [
                {"product_id": pid_18, "quantity": "5", "unit_price": "2000.00"},
                {"product_id": pid_12, "quantity": "3", "unit_price": "1000.00"}
            ]
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        d = r.json()
        assert q(d["subtotal"]) == q("13000.00")
        assert q(d["cgst_total"]) == q("1080.00")
        assert q(d["sgst_total"]) == q("1080.00")
        assert q(d["total_amount"]) == q("15160.00")
        PASS("4.1.3", "GST math verification (multiple items) -> Subtotal=13000, CGST=1080, SGST=1080, Total=15160")
    run_test("4.1.3", "Multiple items GST math", t4_1_3)

    # 4.1.4 Invoice number sequence
    def t4_1_4():
        # Create fresh user to verify 0001, 0002, 0003
        email_seq = rand_email()
        client.post("/api/v1/auth/register", json={
            "email": email_seq,
            "password": "SecurePass1",
            "full_name": "Sequence User",
            "business_name": "Sequence Biz"
        })
        tok_seq = client.post("/api/v1/auth/login", json={"email": email_seq, "password": "SecurePass1"}).json()["access_token"]
        HSEQ = get_auth_header(tok_seq)

        # Customer & Product
        c_res = client.post("/api/v1/billing/customers", headers=HSEQ, json={"name": "Seq Customer"}).json()
        p_res = client.post("/api/v1/billing/products", headers=HSEQ, json={"name": "Seq Prod", "base_price": "100", "gst_rate": "18"}).json()

        year = datetime.utcnow().year
        inv_numbers = []
        for i in range(3):
            r = client.post("/api/v1/billing/invoices", headers=HSEQ, json={
                "customer_id": c_res["id"],
                "gst_type": "INTRA",
                "items": [{"product_id": p_res["id"], "quantity": "1", "unit_price": "100.00"}]
            })
            assert r.status_code in (200, 201)
            inv_numbers.append(r.json()["invoice_number"])

        expected = [f"INV-{year}-0001", f"INV-{year}-0002", f"INV-{year}-0003"]
        assert inv_numbers == expected, f"Invoice sequence mismatch: expected {expected}, got {inv_numbers}"
        PASS("4.1.4", "Invoice number sequence -> INV-YYYY-0001, 0002, 0003 sequential with no gaps")
    run_test("4.1.4", "Invoice number sequence", t4_1_4)

    # 4.1.5 Customer from different user
    def t4_1_5():
        # User B tries using User A's customer_id
        r = client.post("/api/v1/billing/invoices", headers=HB, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "items": [{"product_id": pid_18, "quantity": "1", "unit_price": "100.00"}]
        })
        assert r.status_code == 404, f"Expected 404 for other user's customer, got {r.status_code}"
        PASS("4.1.5", "Customer from different user -> 404 Not Found (Cross-tenant protected)")
    run_test("4.1.5", "Cross-tenant customer invoice creation", t4_1_5)

    # 4.1.6 Product from different user
    def t4_1_6():
        # User B creates own customer, but uses User A's product_id
        cust_b = client.post("/api/v1/billing/customers", headers=HB, json={"name": "User B Customer"}).json()
        r = client.post("/api/v1/billing/invoices", headers=HB, json={
            "customer_id": cust_b["id"],
            "gst_type": "INTRA",
            "items": [{"product_id": pid_18, "quantity": "1", "unit_price": "100.00"}]
        })
        assert r.status_code == 404, f"Expected 404 for other user's product, got {r.status_code}"
        PASS("4.1.6", "Product from different user -> 404 Not Found")
    run_test("4.1.6", "Cross-tenant product invoice creation", t4_1_6)

    # 4.1.7 Empty items array
    def t4_1_7():
        r = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "items": []
        })
        assert r.status_code == 422, f"Expected 422 for empty items, got {r.status_code}"
        PASS("4.1.7", "Empty items array -> 422 Unprocessable Entity")
    run_test("4.1.7", "Empty items array", t4_1_7)

    # 4.1.8 Zero quantity
    def t4_1_8():
        r = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "items": [{"product_id": pid_18, "quantity": "0", "unit_price": "100.00"}]
        })
        assert r.status_code == 422, f"Expected 422 for 0 quantity, got {r.status_code}"
        PASS("4.1.8", "Zero quantity -> 422 Unprocessable Entity")
    run_test("4.1.8", "Zero quantity", t4_1_8)

    # 4.1.9 Non-existent customer_id
    def t4_1_9():
        fake_cid = "00000000-0000-0000-0000-000000000000"
        r = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": fake_cid,
            "gst_type": "INTRA",
            "items": [{"product_id": pid_18, "quantity": "1", "unit_price": "100.00"}]
        })
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        PASS("4.1.9", "Non-existent customer_id -> 404 Not Found")
    run_test("4.1.9", "Non-existent customer_id", t4_1_9)

    # 4.1.10 Invoice with 0% GST product
    def t4_1_10():
        pid_0 = context.get("prod_0_id")
        r = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "items": [{"product_id": pid_0, "quantity": "2", "unit_price": "5000.00"}]
        })
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}"
        d = r.json()
        assert q(d["cgst_total"]) == q("0.00")
        assert q(d["sgst_total"]) == q("0.00")
        assert q(d["igst_total"]) == q("0.00")
        assert q(d["subtotal"]) == q("10000.00")
        assert q(d["total_amount"]) == q("10000.00")
        PASS("4.1.10", "Invoice with 0% GST product -> cgst=0, sgst=0, igst=0, total=subtotal")
    run_test("4.1.10", "0% GST invoice", t4_1_10)


    # ── TEST BLOCK 4.2: INVOICE LIFECYCLE ────────────────────────
    print("\n  -- BLOCK 4.2: INVOICE LIFECYCLE --")

    # 4.2.1 Send invoice (DRAFT -> SENT)
    def t4_2_1():
        inv_id = context["inv_draft_1"]
        r = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=HA)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.json()["status"] == "sent"
        context["inv_sent_1"] = inv_id
        PASS("4.2.1", "Send invoice (DRAFT -> SENT) -> 200 OK, status='sent'")
    run_test("4.2.1", "Send invoice", t4_2_1)

    # 4.2.2 Cannot send already SENT invoice
    def t4_2_2():
        inv_id = context["inv_sent_1"]
        r = client.patch(f"/api/v1/invoices/{inv_id}/send", headers=HA)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "").lower()
        assert "draft" in detail or "sent" in detail, f"Expected explanation in detail: {detail}"
        PASS("4.2.2", "Cannot send already SENT invoice -> 400 Bad Request")
    run_test("4.2.2", "Cannot send already SENT invoice", t4_2_2)

    # 4.2.3 Cannot send PAID invoice
    def t4_2_3():
        # Create fresh invoice, send, pay in full
        r_inv = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "items": [{"product_id": pid_18, "quantity": "1", "unit_price": "1000.00"}]
        }).json()
        client.patch(f"/api/v1/invoices/{r_inv['id']}/send", headers=HA)
        client.post("/api/v1/payments", headers=HA, json={
            "sales_invoice_id": r_inv["id"],
            "customer_id": cid_a,
            "amount": r_inv["total_amount"],
            "payment_method": "bank_transfer",
            "direction": "incoming",
            "payment_date": datetime.utcnow().isoformat()
        })
        context["paid_invoice_id"] = r_inv["id"]

        # Try to send PAID invoice
        r_send = client.patch(f"/api/v1/invoices/{r_inv['id']}/send", headers=HA)
        assert r_send.status_code == 400, f"Expected 400 sending PAID invoice, got {r_send.status_code}"
        PASS("4.2.3", "Cannot send PAID invoice -> 400 Bad Request")
    run_test("4.2.3", "Cannot send PAID invoice", t4_2_3)

    # 4.2.4 Cancel DRAFT invoice
    def t4_2_4():
        r_draft = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "items": [{"product_id": pid_18, "quantity": "1", "unit_price": "500.00"}]
        }).json()
        r = client.patch(f"/api/v1/invoices/{r_draft['id']}/cancel", headers=HA)
        assert r.status_code == 200, f"Expected 200 cancelling DRAFT, got {r.status_code}: {r.text}"
        assert r.json()["status"] == "cancelled"
        PASS("4.2.4", "Cancel DRAFT invoice -> 200 OK, status='cancelled'")
    run_test("4.2.4", "Cancel DRAFT invoice", t4_2_4)

    # 4.2.5 Cancel SENT invoice
    def t4_2_5():
        r_sent = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "items": [{"product_id": pid_18, "quantity": "1", "unit_price": "500.00"}]
        }).json()
        client.patch(f"/api/v1/invoices/{r_sent['id']}/send", headers=HA)
        r = client.patch(f"/api/v1/invoices/{r_sent['id']}/cancel", headers=HA)
        assert r.status_code == 200, f"Expected 200 cancelling SENT, got {r.status_code}: {r.text}"
        assert r.json()["status"] == "cancelled"
        PASS("4.2.5", "Cancel SENT invoice -> 200 OK, status='cancelled'")
    run_test("4.2.5", "Cancel SENT invoice", t4_2_5)

    # 4.2.6 Cannot cancel PAID invoice
    def t4_2_6():
        paid_id = context["paid_invoice_id"]
        r = client.patch(f"/api/v1/invoices/{paid_id}/cancel", headers=HA)
        assert r.status_code == 400, f"Expected 400 cancelling PAID, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "").lower()
        assert "refund" in detail, f"Error should mention refund process: {detail}"
        PASS("4.2.6", "Cannot cancel PAID invoice -> 400 Bad Request (mentions refund process)")
    run_test("4.2.6", "Cannot cancel PAID invoice", t4_2_6)

    # 4.2.7 List invoices by status filter
    def t4_2_7():
        r_draft = client.get("/api/v1/invoices?status=draft", headers=HA)
        assert r_draft.status_code == 200
        drafts = as_list(r_draft.json(), "invoices")
        for inv in drafts:
            assert inv["status"] == "draft", f"Non-draft invoice in drafts filter: {inv['status']}"

        r_paid = client.get("/api/v1/invoices?status=paid", headers=HA)
        assert r_paid.status_code == 200
        paids = as_list(r_paid.json(), "invoices")
        for inv in paids:
            assert inv["status"] == "paid", f"Non-paid invoice in paids filter: {inv['status']}"

        PASS("4.2.7", "List invoices by status filter -> accurately filters 'draft' and 'paid'")
    run_test("4.2.7", "List invoices by status filter", t4_2_7)

    # 4.2.8 Overdue detection
    def t4_2_8():
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        r_od = client.post("/api/v1/billing/invoices", headers=HA, json={
            "customer_id": cid_a,
            "gst_type": "INTRA",
            "due_date": yesterday,
            "items": [{"product_id": pid_18, "quantity": "1", "unit_price": "2000.00"}]
        }).json()
        client.patch(f"/api/v1/invoices/{r_od['id']}/send", headers=HA)

        # Trigger check-overdue
        r_check = client.post("/api/v1/invoices/check-overdue", headers=HA)
        assert r_check.status_code == 200, f"check-overdue returned {r_check.status_code}: {r_check.text}"
        data_check = r_check.json()
        assert data_check.get("count", 0) >= 1, "At least 1 invoice should be marked OVERDUE"

        # Check DB / API status
        r_fetch = client.get(f"/api/v1/billing/invoices/{r_od['id']}", headers=HA)
        assert r_fetch.json()["status"] == "overdue", f"Invoice status should be 'overdue', got {r_fetch.json()['status']}"
        PASS("4.2.8", "Overdue detection -> Scans past due invoices and transitions them to 'overdue'")
    run_test("4.2.8", "Overdue detection", t4_2_8)


# ═══════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*65)
    print("  AI VIRTUAL CFO -- DEDICATED PHASES 1-4 TEST SUITE")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    test_phase_1()
    test_phase_2()
    test_phase_3()
    test_phase_4()

    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    total = len(results)

    print("\n" + "="*65)
    print(f"  PHASES 1-4 SUMMARY: {len(passed)}/{total} PASSED")
    print("="*65)

    if failed:
        print(f"\n  FAILURES ({len(failed)}):")
        print("  " + "-"*56)
        for test_id, _, reason in failed:
            print(f"  [FAIL] {test_id} => {reason}")
    else:
        print("\n  ALL 59 TESTS FOR PHASES 1 TO 4 PASSED SUCCESSFULLY!")

    print(f"\n  Passed : {len(passed)}")
    print(f"  Failed : {len(failed)}")
    print(f"  Total  : {total}")
    print("="*65 + "\n")

    sys.exit(0 if not failed else 1)
