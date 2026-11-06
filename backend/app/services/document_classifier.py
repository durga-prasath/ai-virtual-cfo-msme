# backend/app/services/document_classifier.py

"""
TWO-STAGE DOCUMENT CLASSIFIER

Stage 1: Deterministic rule-based scoring (keyword and pattern matches)
         Supported types:
         - SALARY_SLIP
         - BANK_STATEMENT
         - SALES_INVOICE
         - VENDOR_INVOICE
         - EXPENSE_RECEIPT

Stage 2: Gemini AI fallback (if confidence < 0.65 and GEMINI_API_KEY available)
"""

import re
import json
import logging
from typing import Tuple, Dict, Any

from app.schemas.ocr_schema import DocumentTypeEnum
from app.core.config import settings

logger = logging.getLogger(__name__)

KEYWORDS: Dict[DocumentTypeEnum, list] = {
    DocumentTypeEnum.SALARY_SLIP: [
        r"\b(salary|payslip|pay\s*slip|earnings|deductions|basic\s*pay|hra|provident\s*fund|pf\s*no|employee\s*(?:id|code|name)|net\s*pay|gross\s*pay)\b"
    ],
    DocumentTypeEnum.BANK_STATEMENT: [
        r"\b(bank\s*statement|account\s*statement|statement\s*of\s*account|account\s*number|a/c\s*no|ifsc|opening\s*balance|closing\s*balance|withdrawal|deposit|cheque\s*no|utr|neft|rtgs|imps)\b"
    ],
    DocumentTypeEnum.SALES_INVOICE: [
        r"\b(tax\s*invoice|sales\s*invoice|bill\s*of\s*supply|invoice\s*to|billed\s*to|buyer|consignee|place\s*of\s*supply|customer|client)\b"
    ],
    DocumentTypeEnum.VENDOR_INVOICE: [
        r"\b(vendor|supplier|purchase\s*invoice|billed\s*from|seller|vendor\s*code|purchase\s*order|po\s*no|supplier\s*ref)\b"
    ],
    DocumentTypeEnum.EXPENSE_RECEIPT: [
        r"\b(receipt|cash\s*receipt|payment\s*receipt|store\s*receipt|pos\s*receipt|tax\s*receipt|counter\s*sale|subtotal|table\s*no|merchant)\b"
    ]
}


def classify_by_rules(text: str) -> Tuple[DocumentTypeEnum, float]:
    """
    Stage 1: Rule-based classification.
    Returns (DocumentTypeEnum, confidence: 0.0 - 1.0).
    """
    if not text or not text.strip():
        return DocumentTypeEnum.UNKNOWN, 0.0

    lower_text = text.lower()
    scores: Dict[DocumentTypeEnum, int] = {dt: 0 for dt in KEYWORDS}

    for dt, patterns in KEYWORDS.items():
        for pat in patterns:
            matches = re.findall(pat, lower_text, re.IGNORECASE)
            scores[dt] += len(matches)

    # Contextual boosters
    has_gstin = bool(re.search(r'\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b', text))
    if has_gstin:
        scores[DocumentTypeEnum.VENDOR_INVOICE] += 2
        scores[DocumentTypeEnum.SALES_INVOICE] += 2

    # Distinguish vendor vs sales invoice
    if re.search(r'\b(billed\s*from|vendor|supplier|purchase\s*order|po\s*no)\b', lower_text):
        scores[DocumentTypeEnum.VENDOR_INVOICE] += 3
    if re.search(r'\b(billed\s*to|buyer|consignee|sales\s*invoice)\b', lower_text):
        scores[DocumentTypeEnum.SALES_INVOICE] += 2

    best_type = DocumentTypeEnum.UNKNOWN
    max_score = 0

    for dt, score in scores.items():
        if score > max_score:
            max_score = score
            best_type = dt

    if max_score == 0:
        return DocumentTypeEnum.UNKNOWN, 0.0

    confidence = min(0.95, round(0.40 + (max_score * 0.08), 2))
    return best_type, confidence


def classify_with_gemini(text: str) -> Tuple[DocumentTypeEnum, float]:
    """
    Stage 2: Gemini AI fallback classification.
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured. Skipping Gemini classification.")
        return DocumentTypeEnum.UNKNOWN, 0.0

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL or "gemini-1.5-flash")

        prompt = f"""
You are an expert Indian MSME financial document classifier.
Classify the following extracted document text into exactly ONE of these categories:
- SALARY_SLIP
- BANK_STATEMENT
- SALES_INVOICE
- VENDOR_INVOICE
- EXPENSE_RECEIPT
- UNKNOWN

Respond ONLY with a JSON object in this exact format:
{{"document_type": "<TYPE>", "confidence": <float between 0.0 and 1.0>, "reason": "<short reason>"}}

Document text (first 1500 chars):
{text[:1500]}
"""

        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        if text_resp.startswith("```"):
            text_resp = re.sub(r"^```(?:json)?\n|\n```$", "", text_resp, flags=re.MULTILINE).strip()

        data = json.loads(text_resp)
        dt_str = data.get("document_type", "UNKNOWN")
        conf = float(data.get("confidence", 0.5))

        try:
            return DocumentTypeEnum(dt_str), conf
        except ValueError:
            return DocumentTypeEnum.UNKNOWN, conf

    except Exception as e:
        logger.warning(f"Gemini classification failed: {e}")
        return DocumentTypeEnum.UNKNOWN, 0.0


def classify_document(text: str) -> Tuple[DocumentTypeEnum, float]:
    """
    Primary classification entry point.
    Runs Stage 1 rules; falls back to Gemini Stage 2 if confidence < 0.65.
    """
    doc_type, conf = classify_by_rules(text)

    if (doc_type == DocumentTypeEnum.UNKNOWN or conf < 0.65) and settings.GEMINI_API_KEY:
        logger.info(f"Low confidence ({conf}) on rule-based classification. Invoking Gemini AI...")
        ai_type, ai_conf = classify_with_gemini(text)
        if ai_type != DocumentTypeEnum.UNKNOWN and ai_conf >= conf:
            return ai_type, ai_conf

    return doc_type, conf
