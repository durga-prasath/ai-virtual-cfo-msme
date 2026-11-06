# backend/tests/run_phase6_scanner_tests.py
"""
PHASE 6 TEST SUITE - Smart Document Scanner & OpenCV Pipeline
"""
import sys
import io
import random
import string
import numpy as np
import cv2

sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from main import app
from app.schemas.ocr_schema import DocumentTypeEnum
from app.services.ocr_service import (
    load_image_from_bytes,
    convert_to_grayscale,
    remove_noise,
    apply_adaptive_threshold,
    deskew_image,
    remove_borders,
    enhance_for_tesseract,
    preprocess_image_pipeline,
)
from app.services.document_classifier import classify_by_rules
from app.services.document_processor import process_document

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
    return f"ocr_test_{random.randint(10000,99999)}@cfodemo.com"

# 1. OpenCV Preprocessing Tests
def t01_opencv_pipeline():
    # Create a synthetic 100x100 white image with black text rectangle
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.putText(img, 'TEST', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    success, encoded = cv2.imencode('.png', img)
    assert success
    file_bytes = encoded.tobytes()

    loaded = load_image_from_bytes(file_bytes)
    assert loaded is not None and loaded.shape == (100, 100, 3)

    gray = convert_to_grayscale(loaded)
    assert len(gray.shape) == 2

    denoised = remove_noise(gray)
    assert denoised.shape == gray.shape

    binary = apply_adaptive_threshold(denoised)
    assert binary.shape == gray.shape

    deskewed = deskew_image(binary)
    assert deskewed.shape == binary.shape

    bordered = remove_borders(deskewed, margin=5)
    assert bordered.shape == (90, 90)

    enhanced = enhance_for_tesseract(bordered)
    assert enhanced.shape == bordered.shape

    full_pipeline = preprocess_image_pipeline(file_bytes)
    assert full_pipeline is not None

# 2. Document Classification Tests
def t02_rule_classification_vendor_invoice():
    text = "TAX INVOICE\nVendor: Apex Traders\nSupplier Ref: VEND-001\nGSTIN: 27AABCV1234F1Z1\nTotal Amount: Rs 15,000.00"
    doc_type, conf = classify_by_rules(text)
    assert doc_type == DocumentTypeEnum.VENDOR_INVOICE
    assert conf >= 0.5

def t03_rule_classification_salary_slip():
    text = "MONTHLY PAYSLIP\nEmployee Name: Rahul Sharma\nBasic Pay: 40000\nHRA: 15000\nProvident Fund: 3600\nNet Pay: 51400"
    doc_type, conf = classify_by_rules(text)
    assert doc_type == DocumentTypeEnum.SALARY_SLIP
    assert conf >= 0.5

def t04_rule_classification_bank_statement():
    text = "HDFC BANK STATEMENT OF ACCOUNT\nA/C No: 50100234567891\nIFSC: HDFC0000123\nOpening Balance: 2,50,000.00\nClosing Balance: 3,10,000.00"
    doc_type, conf = classify_by_rules(text)
    assert doc_type == DocumentTypeEnum.BANK_STATEMENT
    assert conf >= 0.5

def t05_rule_classification_expense_receipt():
    text = "CAFE COFFEE DAY\nCash Receipt\nTable No: 4\nSubtotal: 450.00\nTotal: 472.50\nThank you visit again"
    doc_type, conf = classify_by_rules(text)
    assert doc_type == DocumentTypeEnum.EXPENSE_RECEIPT
    assert conf >= 0.5

# 3. Document Processor Tests
def t06_document_processor_fields():
    text = "TAX INVOICE\nApex Suppliers Pvt Ltd\nInvoice No: INV-2026-99\nDate: 12/09/2026\nGSTIN: 27AABCV1234F1Z1\nSubtotal: 10,000.00\nCGST: 900.00\nSGST: 900.00\nGrand Total: 11,800.00"
    resp = process_document(text)
    assert resp.document_type in (DocumentTypeEnum.VENDOR_INVOICE, DocumentTypeEnum.SALES_INVOICE)
    assert resp.fields.get("invoice_number").value == "INV-2026-99"
    assert resp.fields.get("total_amount").value == "11800.00"
    assert resp.fields.get("cgst_amount").value == "900.00"
    assert resp.fields.get("sgst_amount").value == "900.00"

# 4. API Endpoints Tests
def t07_auth_setup():
    email = rand_email()
    pwd = "TestPass@123"
    r = client.post('/api/v1/auth/register', json={
        'full_name': 'Scanner Test User',
        'email': email,
        'password': pwd,
        'business_name': 'Scanner Ltd',
        'gstin': rand_gstin(),
    })
    assert r.status_code in (200, 201)
    r_login = client.post('/api/v1/auth/login', json={'email': email, 'password': pwd})
    token = r_login.json()['access_token']
    context['headers'] = {'Authorization': f'Bearer {token}'}

def t08_api_supported_types():
    r = client.get('/api/v1/ocr/supported-types')
    assert r.status_code == 200
    data = r.json()
    assert 'supported_types' in data
    assert len(data['supported_types']) >= 5

def t09_api_scan_image():
    # Generate dummy image bytes with OpenCV
    img = np.ones((200, 400, 3), dtype=np.uint8) * 255
    cv2.putText(img, 'INVOICE INV-889', (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(img, 'TOTAL 5000.00', (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    _, enc = cv2.imencode('.png', img)
    file_bytes = enc.tobytes()

    files = {'file': ('test_bill.png', io.BytesIO(file_bytes), 'image/png')}
    r = client.post('/api/v1/ocr/scan', files=files, headers=context['headers'])
    assert r.status_code == 200
    data = r.json()
    assert 'document_type' in data
    assert 'fields' in data
    assert 'raw_text_preview' in data

def t10_api_confirm_vendor_invoice():
    payload = {
        'document_type': DocumentTypeEnum.VENDOR_INVOICE.value,
        'confirmed_fields': {
            'vendor_name': 'Test Vendor Supplies',
            'vendor_gstin': rand_gstin(),
            'invoice_number': f'TEST-INV-{random.randint(100,999)}',
            'total_amount': '25000.00',
            'subtotal': '20000.00',
            'cgst_amount': '2500.00',
            'sgst_amount': '2500.00',
            'confidence': 95.0,
        },
        'notes': 'Test invoice confirmed from OCR scanner',
    }
    r = client.post('/api/v1/ocr/confirm', json=payload, headers=context['headers'])
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'success'
    assert data['created_entity_type'] == 'PurchaseInvoice'
    assert data['entity_id'] is not None

def t11_api_confirm_expense_receipt():
    payload = {
        'document_type': DocumentTypeEnum.EXPENSE_RECEIPT.value,
        'confirmed_fields': {
            'merchant_name': 'Office Stationary Mart',
            'total_amount': '3450.00',
        },
        'notes': 'Printer paper and cartridges',
    }
    r = client.post('/api/v1/ocr/confirm', json=payload, headers=context['headers'])
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'success'
    assert data['created_entity_type'] == 'RevenueLedger'
    assert data['entity_id'] is not None

if __name__ == '__main__':
    print('=' * 65)
    print('  PHASE 6 TEST SUITE - SMART DOCUMENT SCANNER')
    print('=' * 65)
    tests = [
        ('T01  OpenCV 7-step Preprocessing Pipeline', t01_opencv_pipeline),
        ('T02  Rule Classifier: Vendor Invoice',     t02_rule_classification_vendor_invoice),
        ('T03  Rule Classifier: Salary Slip',        t03_rule_classification_salary_slip),
        ('T04  Rule Classifier: Bank Statement',     t04_rule_classification_bank_statement),
        ('T05  Rule Classifier: Expense Receipt',    t05_rule_classification_expense_receipt),
        ('T06  Document Processor: Field Detection', t06_document_processor_fields),
        ('T07  User Auth Setup for Scanner',         t07_auth_setup),
        ('T08  API: GET /ocr/supported-types',       t08_api_supported_types),
        ('T09  API: POST /ocr/scan (Image)',         t09_api_scan_image),
        ('T10  API: POST /ocr/confirm (Vendor Inv)', t10_api_confirm_vendor_invoice),
        ('T11  API: POST /ocr/confirm (Expense)',    t11_api_confirm_expense_receipt),
    ]
    for name, fn in tests:
        run(name, fn)
    print('-' * 65)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  Results: {passed} passed  |  {failed} failed  |  {len(results)} total")
    print('-' * 65)
    if failed == 0:
        print('  ALL 11 PHASE 6 TESTS PASSED!')
    sys.exit(0 if failed == 0 else 1)