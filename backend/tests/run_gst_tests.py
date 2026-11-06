# backend/tests/run_gst_tests.py

"""
COMPREHENSIVE TEST SUITE: GST REPORTING & COMPLIANCE (PHASE 5)

Tests:
1. User registration & authentication
2. Business profile & customer creation (B2B registered vs B2C unregistered)
3. Product catalog creation with GST rates (18%, 12%, 5%)
4. Sales invoice creation with automated tax calculations
5. Invoice lifecycle transitions (SENT, PAID, DRAFT, CANCELLED)
6. Purchase invoice creation for Input Tax Credit (ITC)
7. GSTR-1 Outward Supplies return generation (B2B, B2CL, B2CS, HSN, Doc summary)
8. GSTR-1 Government Portal JSON generation
9. GSTR-3B Monthly Summary return generation (Tables 3.1, 3.2, 4.0, 5.1, 6.1)
10. GSTR-3B Government Portal JSON generation
11. GST Reconciliation & Discrepancy Audit
12. Real-time Tax Liability Summary for Virtual CFO Dashboard
13. Return filing lifecycle (READY_TO_FILE -> FILED) & double filing prevention
14. Historical records list query
15. Multi-tenant user data isolation
16. Period format validation
"""

import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime, date

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from app.db.database import SessionLocal
from app.models.business import Business, BusinessType
from app.models.vendor import Vendor
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
from app.models.sales_invoice import SalesInvoice, InvoiceStatus

client = TestClient(app)

def run_tests():
    print("=" * 70)
    print("STARTING PHASE 5: GST COMPLIANCE & REPORTING TEST SUITE")
    print("=" * 70)

    unique_id = uuid.uuid4().hex[:8]
    email_a = f"gst_cfo_user_{unique_id}@example.com"
    email_b = f"gst_isolated_user_{unique_id}@example.com"
    password = "SecurePassword123!"

    # ──────────────────────────────────────────────────────────
    # 1. REGISTER USERS
    # ──────────────────────────────────────────────────────────
    print("\n[1/16] Testing User Registration...")
    res = client.post("/api/v1/auth/register", json={
        "email": email_a,
        "password": password,
        "full_name": "Tamil Nadu MSME Tech",
        "phone": "9876543210",
        "business_name": "TN MSME Tech Solutions"
    })
    assert res.status_code == 201, f"User A registration failed: {res.text}"
    user_a_id = res.json()["id"]

    res_b = client.post("/api/v1/auth/register", json={
        "email": email_b,
        "password": password,
        "full_name": "Isolated Competitor",
        "phone": "9876543211",
        "business_name": "Isolated Corp"
    })
    assert res_b.status_code == 201, f"User B registration failed: {res_b.text}"
    user_b_id = res_b.json()["id"]
    print("  [PASS] User A & User B registered successfully")

    # ──────────────────────────────────────────────────────────
    # 2. LOGIN & ACQUIRE TOKENS
    # ──────────────────────────────────────────────────────────
    print("\n[2/16] Testing Authentication & Token Generation...")
    login_a = client.post("/api/v1/auth/login", json={"email": email_a, "password": password})
    assert login_a.status_code == 200
    token_a = login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    login_b = client.post("/api/v1/auth/login", json={"email": email_b, "password": password})
    assert login_b.status_code == 200
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    print("  [PASS] JWT tokens issued and verified")

    # ──────────────────────────────────────────────────────────
    # 3. SET UP BUSINESS PROFILE WITH VALID GSTIN
    # ──────────────────────────────────────────────────────────
    print("\n[3/16] Configuring Business Profile...")
    db = SessionLocal()
    import random
    rand_num = f"{random.randint(1000, 9999)}"
    seller_gstin = f"33AAATE{rand_num}F1Z1"  # 33 = Tamil Nadu
    cust_gstin = f"33AAACB{rand_num}F1Z2"
    biz = Business(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_a_id),
        business_name="TN MSME Tech Solutions",
        legal_name="TN MSME Tech Solutions Pvt Ltd",
        business_type=BusinessType.PRIVATE_LIMITED,
        gstin=seller_gstin,
        state="Tamil Nadu",
        country="India"
    )
    db.add(biz)
    db.commit()
    db.close()
    print(f"  [PASS] Business linked with GSTIN: {seller_gstin} (State: Tamil Nadu)")

    # ──────────────────────────────────────────────────────────
    # 4. CREATE CUSTOMERS (B2B, B2C INTER-STATE, B2C INTRA-STATE)
    # ──────────────────────────────────────────────────────────
    print("\n[4/16] Creating Customers (B2B Registered vs B2C Unregistered)...")
    # Customer 1: Registered B2B in Tamil Nadu (Intra-state)
    res_c1 = client.post("/api/v1/billing/customers", headers=headers_a, json={
        "name": "Sri Balaji Traders (B2B)",
        "email": f"balaji_{rand_num}@example.com",
        "phone": "9443211234",
        "gstin": cust_gstin,
        "state": "Tamil Nadu",
        "city": "Chennai"
    })
    assert res_c1.status_code == 201, f"Customer 1 creation failed: {res_c1.text}"
    cust_b2b_id = res_c1.json()["id"]

    # Customer 2: Unregistered in Karnataka (Inter-state)
    res_c2 = client.post("/api/v1/billing/customers", headers=headers_a, json={
        "name": "Bangalore Retail Shopper (B2C Large)",
        "email": "shopper@example.com",
        "phone": "9880112233",
        "state": "Karnataka",
        "city": "Bengaluru"
    })
    assert res_c2.status_code == 201, f"Customer 2 creation failed: {res_c2.text}"
    cust_b2cl_id = res_c2.json()["id"]

    # Customer 3: Unregistered in Tamil Nadu (Intra-state)
    res_c3 = client.post("/api/v1/billing/customers", headers=headers_a, json={
        "name": "Local Consumer (B2C Small)",
        "phone": "9123456780",
        "state": "Tamil Nadu",
        "city": "Madurai"
    })
    assert res_c3.status_code == 201
    cust_b2cs_id = res_c3.json()["id"]
    print("  [PASS] Created B2B (registered), B2C Large (inter-state), and B2C Small customers")

    # ──────────────────────────────────────────────────────────
    # 5. CREATE PRODUCTS WITH GST RATES (18%, 12%, 5%)
    # ──────────────────────────────────────────────────────────
    print("\n[5/16] Creating Products with HSN Codes and GST Slabs...")
    p1 = client.post("/api/v1/billing/products", headers=headers_a, json={
        "name": "Server Maintenance Service",
        "hsn_code": "84713010",
        "base_price": "10000.00",
        "gst_rate": "18.00",
        "unit": "HOUR"
    }).json()
    prod_18_id = p1["id"]

    p2 = client.post("/api/v1/billing/products", headers=headers_a, json={
        "name": "Power Backup Supply",
        "hsn_code": "85044090",
        "base_price": "50000.00",
        "gst_rate": "12.00",
        "unit": "PCS"
    }).json()
    prod_12_id = p2["id"]

    p3 = client.post("/api/v1/billing/products", headers=headers_a, json={
        "name": "Eco Packing Material",
        "hsn_code": "10063010",
        "base_price": "2000.00",
        "gst_rate": "5.00",
        "unit": "KG"
    }).json()
    prod_5_id = p3["id"]
    print("  [PASS] Products created with 18%, 12%, and 5% GST slabs")

    # Target test period
    test_period = datetime.utcnow().strftime("%m-%Y")

    # ──────────────────────────────────────────────────────────
    # 6. CREATE SALES INVOICES & TRIGGER LIFECYCLE
    # ──────────────────────────────────────────────────────────
    print(f"\n[6/16] Generating Sales Invoices for Period {test_period}...")

    # Invoice 1: B2B Intra-state (Customer 1, 18% GST). Subtotal = ₹10,000. CGST=₹900, SGST=₹900, Total=₹11,800
    inv1_res = client.post("/api/v1/billing/invoices", headers=headers_a, json={
        "customer_id": cust_b2b_id,
        "gst_type": "INTRA",
        "items": [{"product_id": prod_18_id, "quantity": 1, "unit_price": "10000.00"}]
    })
    assert inv1_res.status_code == 201
    inv1_id = inv1_res.json()["id"]
    # Send invoice so it becomes SENT
    client.patch(f"/api/v1/invoices/{inv1_id}/send", headers=headers_a)

    # Invoice 2: B2C Large Inter-state (Customer 2, 12% GST). Qty 6 @ ₹50,000 = ₹3,00,000 (> ₹2.5L). IGST=₹36,000, Total=₹3,36,000
    inv2_res = client.post("/api/v1/billing/invoices", headers=headers_a, json={
        "customer_id": cust_b2cl_id,
        "gst_type": "INTER",
        "items": [{"product_id": prod_12_id, "quantity": 6, "unit_price": "50000.00"}]
    })
    assert inv2_res.status_code == 201
    inv2_id = inv2_res.json()["id"]
    client.patch(f"/api/v1/invoices/{inv2_id}/send", headers=headers_a)

    # Invoice 3: B2C Small Intra-state (Customer 3, 5% GST). Subtotal = ₹2,000. CGST=₹50, SGST=₹50, Total=₹2,100
    inv3_res = client.post("/api/v1/billing/invoices", headers=headers_a, json={
        "customer_id": cust_b2cs_id,
        "gst_type": "INTRA",
        "items": [{"product_id": prod_5_id, "quantity": 1, "unit_price": "2000.00"}]
    })
    assert inv3_res.status_code == 201
    inv3_id = inv3_res.json()["id"]
    client.patch(f"/api/v1/invoices/{inv3_id}/send", headers=headers_a)
    # Record full payment so Invoice 3 becomes PAID
    client.post("/api/v1/payments", headers=headers_a, json={
        "sales_invoice_id": inv3_id,
        "amount": "2100.00",
        "payment_method": "upi",
        "direction": "incoming",
        "transaction_reference": f"UPI-TEST-{unique_id}"
    })

    # Invoice 4: Draft invoice (Must NOT be included in GST outward supplies)
    inv4_res = client.post("/api/v1/billing/invoices", headers=headers_a, json={
        "customer_id": cust_b2b_id,
        "gst_type": "INTRA",
        "items": [{"product_id": prod_18_id, "quantity": 1, "unit_price": "5000.00"}]
    })
    assert inv4_res.status_code == 201
    inv4_id = inv4_res.json()["id"]  # Stays DRAFT

    # Invoice 5: Cancelled invoice (Counts towards Document summary cancelled count)
    inv5_res = client.post("/api/v1/billing/invoices", headers=headers_a, json={
        "customer_id": cust_b2cs_id,
        "gst_type": "INTRA",
        "items": [{"product_id": prod_5_id, "quantity": 1, "unit_price": "1000.00"}]
    })
    assert inv5_res.status_code == 201
    inv5_id = inv5_res.json()["id"]
    client.patch(f"/api/v1/invoices/{inv5_id}/cancel", headers=headers_a)

    print("  [PASS] Invoices created across SENT (B2B, B2CL), PAID (B2CS), DRAFT, and CANCELLED statuses")

    # ──────────────────────────────────────────────────────────
    # 7. CREATE PURCHASE INVOICES (INPUT TAX CREDIT - ITC)
    # ──────────────────────────────────────────────────────────
    print("\n[7/16] Recording Purchase Invoices for Eligible ITC...")
    db = SessionLocal()
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_a_id),
        name="Dell Hardware Supply",
        gstin="29AAACD9999F1Z5",
        city="Bengaluru",
        state="Karnataka"
    )
    db.add(vendor)
    db.commit()

    # Purchase Invoice: Subtotal ₹1,00,000 with IGST ₹18,000 (Status: RECEIVED)
    pinv = PurchaseInvoice(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_a_id),
        vendor_id=vendor.id,
        invoice_number=f"PINV-{unique_id}-001",
        vendor_invoice_number=f"DELL-INV-{unique_id}",
        invoice_date=datetime.utcnow(),
        status=PurchaseInvoiceStatus.RECEIVED,
        subtotal=Decimal('100000.00'),
        tax_amount=Decimal('18000.00'),
        total_amount=Decimal('118000.00'),
        igst_total=Decimal('18000.00'),
        cgst_total=Decimal('0.00'),
        sgst_total=Decimal('0.00'),
        amount_paid=Decimal('0.00'),
        amount_due=Decimal('118000.00')
    )
    db.add(pinv)
    db.commit()
    db.close()
    print("  [PASS] Purchase Invoice logged: Rs. 1,00,000 with Rs. 18,000 eligible IGST credit")

    # ──────────────────────────────────────────────────────────
    # 8. TEST GSTR-1 GENERATION
    # ──────────────────────────────────────────────────────────
    print(f"\n[8/16] Testing GSTR-1 Generation for period {test_period}...")
    gstr1_res = client.get(f"/api/v1/gst/gstr1?return_period={test_period}", headers=headers_a)
    assert gstr1_res.status_code == 200, f"GSTR-1 generation failed: {gstr1_res.text}"
    gstr1 = gstr1_res.json()

    # Verify B2B classification
    assert len(gstr1["b2b_invoices"]) == 1, f"Expected 1 B2B invoice, got {len(gstr1['b2b_invoices'])}"
    assert gstr1["b2b_invoices"][0]["customer_gstin"] == cust_gstin
    assert Decimal(str(gstr1["b2b_invoices"][0]["total_amount"])) == Decimal('11800.00')

    # Verify B2C Large classification (Inter-state > 2.5L)
    assert len(gstr1["b2cl_invoices"]) == 1, f"Expected 1 B2CL invoice, got {len(gstr1['b2cl_invoices'])}"
    assert Decimal(str(gstr1["b2cl_invoices"][0]["total_amount"])) == Decimal('336000.00')

    # Verify B2C Small classification
    assert len(gstr1["b2cs_summaries"]) >= 1, "Expected at least 1 B2CS summary"
    assert Decimal(str(gstr1["b2cs_summaries"][0]["taxable_value"])) == Decimal('2000.00')

    # Verify Total Invoices (SENT + PAID = 3; DRAFT and CANCELLED excluded from supply count)
    assert gstr1["total_invoices"] == 3, f"Expected 3 active invoices, got {gstr1['total_invoices']}"
    # Total Taxable = 10,000 + 3,00,000 + 2,000 = 3,12,000
    assert Decimal(str(gstr1["total_taxable_value"])) == Decimal('312000.00')
    # Total Tax = 1,800 + 36,000 + 100 = 37,900
    assert Decimal(str(gstr1["total_tax"])) == Decimal('37900.00')

    # Verify Document Summary (from serial, to serial, total=4 including cancelled, cancelled=1, net=3)
    doc_sum = gstr1["doc_summary"]
    assert doc_sum["total_number"] == 4
    assert doc_sum["cancelled_number"] == 1
    assert doc_sum["net_issued_number"] == 3

    print(f"  [PASS] GSTR-1 Verified: Taxable Rs. {gstr1['total_taxable_value']}, Total Tax Rs. {gstr1['total_tax']}")
    print(f"    - B2B Invoices: {len(gstr1['b2b_invoices'])}")
    print(f"    - B2C Large Invoices: {len(gstr1['b2cl_invoices'])}")
    print(f"    - B2C Small Summaries: {len(gstr1['b2cs_summaries'])}")
    print(f"    - HSN Slabs aggregated: {len(gstr1['hsn_summary'])}")
    print(f"    - Doc summary: {doc_sum['net_issued_number']} net issued, {doc_sum['cancelled_number']} cancelled")

    # ──────────────────────────────────────────────────────────
    # 9. TEST GSTR-1 GOVERNMENT PORTAL JSON EXPORT
    # ──────────────────────────────────────────────────────────
    print("\n[9/16] Testing GSTR-1 Portal JSON Payload Export...")
    json_res = client.get(f"/api/v1/gst/gstr1/json?return_period={test_period}", headers=headers_a)
    assert json_res.status_code == 200
    portal_json = json_res.json()
    assert portal_json["gstin"] == seller_gstin
    assert "b2b" in portal_json
    assert "b2cl" in portal_json
    assert "b2cs" in portal_json
    assert "hsn" in portal_json
    assert "doc_issue" in portal_json
    print("  [PASS] GSTR-1 official portal JSON schema verified")

    # ──────────────────────────────────────────────────────────
    # 10. TEST GSTR-3B GENERATION & ITC NETTING
    # ──────────────────────────────────────────────────────────
    print(f"\n[10/16] Testing GSTR-3B Generation for period {test_period}...")
    gstr3b_res = client.get(f"/api/v1/gst/gstr3b?return_period={test_period}", headers=headers_a)
    assert gstr3b_res.status_code == 200, f"GSTR-3B generation failed: {gstr3b_res.text}"
    gstr3b = gstr3b_res.json()

    # Table 3.1 Outward supplies: Taxable Rs. 3,12,000, IGST Rs. 36,000, CGST Rs. 950, SGST Rs. 950, Total Rs. 37,900
    t3 = gstr3b["table_3_1_outward_supplies"]
    assert Decimal(str(t3["taxable_value"])) == Decimal('312000.00')
    assert Decimal(str(t3["igst"])) == Decimal('36000.00')
    assert Decimal(str(t3["cgst"])) == Decimal('950.00')
    assert Decimal(str(t3["sgst"])) == Decimal('950.00')
    assert Decimal(str(t3["total_tax"])) == Decimal('37900.00')

    # Table 3.2 Inter-state unregistered supplies (Invoice 2: Karnataka, Rs. 3,00,000, IGST Rs. 36,000)
    t32 = gstr3b["table_3_2_inter_state_supplies"]
    assert len(t32) == 1
    assert Decimal(str(t32[0]["taxable_value"])) == Decimal('300000.00')
    assert Decimal(str(t32[0]["igst"])) == Decimal('36000.00')

    # Table 4 Eligible ITC (From Purchase Invoice: IGST Rs. 18,000)
    t4 = gstr3b["table_4_eligible_itc"]
    assert Decimal(str(t4["itc_igst"])) == Decimal('18000.00')
    assert Decimal(str(t4["total_itc"])) == Decimal('18000.00')

    # Table 6.1 Payment of Tax:
    # IGST Liability: Rs. 36,000. Offset by Rs. 18,000 IGST ITC -> Remaining IGST payable = Rs. 18,000
    # CGST Liability: Rs. 950 (No CGST ITC) -> Rs. 950 payable
    # SGST Liability: Rs. 950 (No SGST ITC) -> Rs. 950 payable
    # Net Tax Payable = Rs. 18,000 + Rs. 950 + Rs. 950 = Rs. 19,900
    t6 = gstr3b["table_6_1_payment_of_tax"]
    assert Decimal(str(t6["total_tax_liability"])) == Decimal('37900.00')
    assert Decimal(str(t6["total_itc_utilized"])) == Decimal('18000.00')
    assert Decimal(str(t6["net_tax_payable_igst"])) == Decimal('18000.00')
    assert Decimal(str(t6["net_tax_payable_cgst"])) == Decimal('950.00')
    assert Decimal(str(t6["net_tax_payable_sgst"])) == Decimal('950.00')
    assert Decimal(str(t6["total_net_tax_payable"])) == Decimal('19900.00')

    print(f"  [PASS] GSTR-3B Verified:")
    print(f"    - Output Tax Liability: Rs. {t3['total_tax']}")
    print(f"    - Eligible Input Tax Credit (ITC): Rs. {t4['total_itc']}")
    print(f"    - Net Cash Tax Payable: Rs. {t6['total_net_tax_payable']}")

    # ──────────────────────────────────────────────────────────
    # 11. TEST GSTR-3B GOVERNMENT PORTAL JSON EXPORT
    # ──────────────────────────────────────────────────────────
    print("\n[11/16] Testing GSTR-3B Portal JSON Payload Export...")
    gstr3b_json_res = client.get(f"/api/v1/gst/gstr3b/json?return_period={test_period}", headers=headers_a)
    assert gstr3b_json_res.status_code == 200
    g3b_payload = gstr3b_json_res.json()
    assert g3b_payload["gstin"] == seller_gstin
    assert "sec_sum" in g3b_payload
    print("  [PASS] GSTR-3B official portal JSON schema verified")

    # ──────────────────────────────────────────────────────────
    # 12. TEST GST RECONCILIATION & AUDIT
    # ──────────────────────────────────────────────────────────
    print(f"\n[12/16] Testing GST Reconciliation & Discrepancy Audit for {test_period}...")
    recon_res = client.get(f"/api/v1/gst/reconciliation?return_period={test_period}", headers=headers_a)
    assert recon_res.status_code == 200
    recon = recon_res.json()
    assert Decimal(str(recon["taxable_variance"])) == Decimal('0.00')
    assert Decimal(str(recon["tax_variance"])) == Decimal('0.00')
    # Check that draft invoice warning is noted in discrepancies
    assert any("DRAFT" in d for d in recon["discrepancies"]), "Expected draft invoice warning in audit"
    print("  [PASS] GST Reconciliation completed: GSTR-1 and GSTR-3B outward supplies match perfectly")
    print(f"    - Discrepancy audit alerts: {recon['discrepancies']}")

    # ──────────────────────────────────────────────────────────
    # 13. TEST EXECUTIVE TAX LIABILITY SUMMARY (CFO DASHBOARD)
    # ──────────────────────────────────────────────────────────
    print(f"\n[13/16] Testing Real-Time Tax Liability Query (Dashboard Card 3)...")
    liab_res = client.get(f"/api/v1/gst/liability?return_period={test_period}", headers=headers_a)
    assert liab_res.status_code == 200
    liab = liab_res.json()
    assert Decimal(str(liab["gross_output_tax"])) == Decimal('37900.00')
    assert Decimal(str(liab["total_itc_available"])) == Decimal('18000.00')
    assert Decimal(str(liab["net_tax_payable"])) == Decimal('19900.00')
    assert Decimal(str(liab["total_payable_amount"])) == Decimal('19900.00')
    print(f"  [PASS] Executive Tax Liability: Gross Rs. {liab['gross_output_tax']} - ITC Rs. {liab['total_itc_available']} = Net Rs. {liab['net_tax_payable']}")

    # ──────────────────────────────────────────────────────────
    # 14. TEST FILING LIFECYCLE (READY_TO_FILE -> FILED)
    # ──────────────────────────────────────────────────────────
    print("\n[14/16] Testing GST Return Filing Lifecycle...")
    file_gstr1 = client.post("/api/v1/gst/file", headers=headers_a, json={
        "return_type": "gstr1",
        "return_period": test_period,
        "acknowledgement_number": "ARN12345678901234",
        "tax_paid": "0.00"
    })
    assert file_gstr1.status_code == 200
    g1_rec = file_gstr1.json()
    assert g1_rec["status"] == "filed"
    assert g1_rec["acknowledgement_number"] == "ARN12345678901234"

    file_gstr3b = client.post("/api/v1/gst/file", headers=headers_a, json={
        "return_type": "gstr3b",
        "return_period": test_period,
        "acknowledgement_number": "ARN98765432109876",
        "tax_paid": "19900.00"
    })
    assert file_gstr3b.status_code == 200
    g3_rec = file_gstr3b.json()
    assert g3_rec["status"] == "filed"
    assert Decimal(str(g3_rec["tax_paid"])) == Decimal('19900.00')

    # Verify double filing is rejected
    double_file = client.post("/api/v1/gst/file", headers=headers_a, json={
        "return_type": "gstr1",
        "return_period": test_period,
        "acknowledgement_number": "ARN12345678901234"
    })
    assert double_file.status_code == 400, "Double filing should be rejected"
    print("  [PASS] Returns successfully marked as FILED with ARN; double filing properly blocked")

    # ──────────────────────────────────────────────────────────
    # 15. TEST HISTORICAL RECORDS QUERY
    # ──────────────────────────────────────────────────────────
    print("\n[15/16] Testing Historical GST Records Query...")
    records_res = client.get(f"/api/v1/gst/records?return_period={test_period}", headers=headers_a)
    assert records_res.status_code == 200
    records = records_res.json()
    assert len(records) >= 2
    types = {r["return_type"] for r in records}
    assert "gstr1" in types and "gstr3b" in types
    print(f"  [PASS] Found {len(records)} records for period {test_period}")

    # ──────────────────────────────────────────────────────────
    # 16. TEST DATA ISOLATION & VALIDATION
    # ──────────────────────────────────────────────────────────
    print("\n[16/16] Testing Multi-Tenant Data Isolation & Validation...")
    # User B queries same period -> should have 0 invoices, 0 liability
    b_gstr1 = client.get(f"/api/v1/gst/gstr1?return_period={test_period}", headers=headers_b).json()
    assert b_gstr1["total_invoices"] == 0, "User B saw User A's invoices!"
    assert Decimal(str(b_gstr1["total_taxable_value"])) == Decimal('0.00')

    b_gstr3b = client.get(f"/api/v1/gst/gstr3b?return_period={test_period}", headers=headers_b).json()
    assert Decimal(str(b_gstr3b["table_3_1_outward_supplies"]["total_tax"])) == Decimal('0.00')

    # Test invalid period format
    invalid_res = client.get("/api/v1/gst/gstr1?return_period=2026-04", headers=headers_a)
    assert invalid_res.status_code == 422, "Invalid period format should return 422"

    print("  [PASS] Complete data isolation verified: User B has 0 invoices / 0 liability")
    print("  [PASS] Period format validation (MM-YYYY) strictly enforced")

    print("\n" + "=" * 70)
    print("ALL 16 PHASE 5 GST COMPLIANCE & REPORTING TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
