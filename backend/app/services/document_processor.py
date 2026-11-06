# backend/app/services/document_processor.py

"""
DOCUMENT FIELD EXTRACTION PROCESSOR

Extracts structured fields with per-field confidence based on detected DocumentType.
Works in combination with ocr_service and document_classifier.
"""

import re
from typing import Dict, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.ocr_schema import DocumentTypeEnum, DocumentFieldResult, ScanDocumentResponse
from app.services.document_classifier import classify_document

GSTIN_PATTERN    = re.compile(r'\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b')
PAN_PATTERN      = re.compile(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b')
PHONE_PATTERN    = re.compile(r'(?:Ph|Phone|Tel|Mobile|Mob)[:\s.]*([6-9]\d{9})', re.IGNORECASE)
INV_NUM_PATTERN  = re.compile(r'(?:(?:Tax\s*)?Invoice\s*(?:No|Number|#)|Bill\s*(?:No|Number)|(?:\bINV[-/]))\s*[:.]*\s*([A-Z0-9/-]{3,30})', re.IGNORECASE)
DATE_PATTERN     = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b', re.IGNORECASE)

TOTAL_PATTERN    = re.compile(r'(?:Grand\s*Total|Total\s*Amount|Net\s*Amount|Amount\s*Payable|Total\s*Payable|(?<!Sub)\bTotal)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)', re.IGNORECASE)
SUBTOTAL_PATTERN = re.compile(r'(?:Sub[-\s]?Total|Taxable\s*(?:Value|Amount)|Basic\s*Amount)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)', re.IGNORECASE)
CGST_PATTERN     = re.compile(r'CGST(?:\s*@\s*[\d.]+%)?[^0-9\n]*([\d,]+\.\d{2})', re.IGNORECASE)
SGST_PATTERN     = re.compile(r'SGST(?:\s*@\s*[\d.]+%)?[^0-9\n]*([\d,]+\.\d{2})', re.IGNORECASE)
IGST_PATTERN     = re.compile(r'IGST(?:\s*@\s*[\d.]+%)?[^0-9\n]*([\d,]+\.\d{2})', re.IGNORECASE)

# Salary patterns
BASIC_PATTERN    = re.compile(r'(?:Basic(?:\s*Salary|\s*Pay)?|Basic)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)', re.IGNORECASE)
HRA_PATTERN      = re.compile(r'(?:HRA|House\s*Rent\s*Allowance)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)', re.IGNORECASE)
NET_PAY_PATTERN  = re.compile(r'(?:Net\s*(?:Salary|Pay|Amount))[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)', re.IGNORECASE)
EMP_ID_PATTERN   = re.compile(r'(?:Emp(?:loyee)?\s*(?:ID|Code|No))[:\s]*([A-Z0-9-]+)', re.IGNORECASE)

# Bank statement patterns
ACC_NUM_PATTERN  = re.compile(r'(?:A/c|Account)\s*(?:No|Number)?[:\s]*([0-9]{9,18})', re.IGNORECASE)
IFSC_PATTERN     = re.compile(r'\b([A-Z]{4}0[A-Z0-9]{6})\b')
BALANCE_PATTERN  = re.compile(r'(?:Closing\s*Balance|Available\s*Balance|Balance)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)', re.IGNORECASE)


def _clean_amount(raw: str) -> str:
    try:
        cleaned = re.sub(r'(?i)(Rs\.?|INR|₹)', '', raw)
        cleaned = re.sub(r'[,\s]', '', cleaned).strip()
        if cleaned:
            return str(Decimal(cleaned).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    except Exception:
        pass
    return raw.strip()


def extract_fields(text: str, doc_type: DocumentTypeEnum) -> Dict[str, DocumentFieldResult]:
    fields: Dict[str, DocumentFieldResult] = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1. Invoice extraction (Vendor or Sales)
    if doc_type in (DocumentTypeEnum.VENDOR_INVOICE, DocumentTypeEnum.SALES_INVOICE):
        gstins = GSTIN_PATTERN.findall(text)
        if gstins:
            field_name = "vendor_gstin" if doc_type == DocumentTypeEnum.VENDOR_INVOICE else "customer_gstin"
            fields[field_name] = DocumentFieldResult(value=gstins[0], confidence=95.0, source="regex")
            if len(gstins) > 1:
                alt_name = "customer_gstin" if doc_type == DocumentTypeEnum.VENDOR_INVOICE else "vendor_gstin"
                fields[alt_name] = DocumentFieldResult(value=gstins[1], confidence=90.0, source="regex")

        inv_num_m = INV_NUM_PATTERN.search(text)
        if inv_num_m:
            fields["invoice_number"] = DocumentFieldResult(value=inv_num_m.group(1).strip(), confidence=88.0, source="regex")

        dates = DATE_PATTERN.findall(text)
        if dates:
            fields["invoice_date"] = DocumentFieldResult(value=dates[0], confidence=80.0, source="regex")
            if len(dates) > 1:
                fields["due_date"] = DocumentFieldResult(value=dates[1], confidence=70.0, source="regex")

        tot_m = TOTAL_PATTERN.search(text)
        if tot_m:
            fields["total_amount"] = DocumentFieldResult(value=_clean_amount(tot_m.group(1)), confidence=90.0, source="regex")

        sub_m = SUBTOTAL_PATTERN.search(text)
        if sub_m:
            fields["subtotal"] = DocumentFieldResult(value=_clean_amount(sub_m.group(1)), confidence=85.0, source="regex")

        cgst_m = CGST_PATTERN.search(text)
        if cgst_m:
            fields["cgst_amount"] = DocumentFieldResult(value=_clean_amount(cgst_m.group(1)), confidence=88.0, source="regex")

        sgst_m = SGST_PATTERN.search(text)
        if sgst_m:
            fields["sgst_amount"] = DocumentFieldResult(value=_clean_amount(sgst_m.group(1)), confidence=88.0, source="regex")

        igst_m = IGST_PATTERN.search(text)
        if igst_m:
            fields["igst_amount"] = DocumentFieldResult(value=_clean_amount(igst_m.group(1)), confidence=88.0, source="regex")

        # Name heuristic from first lines
        for line in lines[:5]:
            if len(line) > 3 and not re.search(r'\d{6,}|GST|INVOICE|TAX', line, re.IGNORECASE):
                party_field = "vendor_name" if doc_type == DocumentTypeEnum.VENDOR_INVOICE else "customer_name"
                fields[party_field] = DocumentFieldResult(value=line, confidence=65.0, source="heuristic")
                break

    # 2. Salary Slip
    elif doc_type == DocumentTypeEnum.SALARY_SLIP:
        net_m = NET_PAY_PATTERN.search(text)
        if net_m:
            fields["net_salary"] = DocumentFieldResult(value=_clean_amount(net_m.group(1)), confidence=90.0, source="regex")

        basic_m = BASIC_PATTERN.search(text)
        if basic_m:
            fields["basic_salary"] = DocumentFieldResult(value=_clean_amount(basic_m.group(1)), confidence=85.0, source="regex")

        hra_m = HRA_PATTERN.search(text)
        if hra_m:
            fields["hra"] = DocumentFieldResult(value=_clean_amount(hra_m.group(1)), confidence=85.0, source="regex")

        emp_m = EMP_ID_PATTERN.search(text)
        if emp_m:
            fields["employee_id"] = DocumentFieldResult(value=emp_m.group(1).strip(), confidence=80.0, source="regex")

        dates = DATE_PATTERN.findall(text)
        if dates:
            fields["salary_month"] = DocumentFieldResult(value=dates[0], confidence=75.0, source="regex")

    # 3. Bank Statement
    elif doc_type == DocumentTypeEnum.BANK_STATEMENT:
        acc_m = ACC_NUM_PATTERN.search(text)
        if acc_m:
            fields["account_number"] = DocumentFieldResult(value=acc_m.group(1), confidence=92.0, source="regex")

        ifsc_m = IFSC_PATTERN.search(text)
        if ifsc_m:
            fields["ifsc_code"] = DocumentFieldResult(value=ifsc_m.group(1), confidence=95.0, source="regex")

        bal_m = BALANCE_PATTERN.search(text)
        if bal_m:
            fields["closing_balance"] = DocumentFieldResult(value=_clean_amount(bal_m.group(1)), confidence=88.0, source="regex")

    # 4. Expense Receipt
    elif doc_type == DocumentTypeEnum.EXPENSE_RECEIPT:
        tot_m = TOTAL_PATTERN.search(text)
        if tot_m:
            fields["total_amount"] = DocumentFieldResult(value=_clean_amount(tot_m.group(1)), confidence=90.0, source="regex")
        dates = DATE_PATTERN.findall(text)
        if dates:
            fields["receipt_date"] = DocumentFieldResult(value=dates[0], confidence=80.0, source="regex")
        if lines:
            fields["merchant_name"] = DocumentFieldResult(value=lines[0], confidence=70.0, source="heuristic")

    return fields


def process_document(raw_text: str, page_count: int = 1, engine: str = "opencv+tesseract") -> ScanDocumentResponse:
    doc_type, type_conf = classify_document(raw_text)
    fields = extract_fields(raw_text, doc_type)

    warnings = []
    if not fields:
        warnings.append("No structured fields could be reliably detected from document text.")
    if doc_type == DocumentTypeEnum.UNKNOWN:
        warnings.append("Document classification ambiguous. Please classify manually.")

    # Calculate overall confidence
    if fields:
        overall_conf = round(sum(f.confidence for f in fields.values()) / len(fields), 2)
    else:
        overall_conf = round(type_conf * 100, 2)

    # Suggested action
    action_map = {
        DocumentTypeEnum.VENDOR_INVOICE: "Create Purchase Invoice",
        DocumentTypeEnum.SALES_INVOICE: "Create Sales Invoice",
        DocumentTypeEnum.EXPENSE_RECEIPT: "Post Expense to Revenue Ledger",
        DocumentTypeEnum.SALARY_SLIP: "Post Payroll Expense Entry",
        DocumentTypeEnum.BANK_STATEMENT: "Perform Bank Reconciliation",
        DocumentTypeEnum.UNKNOWN: "Review Document Content"
    }

    return ScanDocumentResponse(
        document_type=doc_type,
        type_confidence=round(type_conf * 100, 2),
        overall_confidence=overall_conf,
        fields=fields,
        raw_text_preview=raw_text[:800],
        suggested_action=action_map.get(doc_type, "Review"),
        warnings=warnings,
        page_count=page_count,
        engine=engine
    )
