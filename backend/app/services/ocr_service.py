# backend/app/services/ocr_service.py

"""
ADVANCED OCR EXTRACTION SERVICE WITH OPENCV PREPROCESSING PIPELINE

Preprocessing Pipeline:
1. load_image_from_bytes(file_bytes) -> cv2 decode
2. convert_to_grayscale(img)
3. remove_noise(gray) -> median blur (3x3)
4. apply_adaptive_threshold(gray) -> Gaussian adaptive threshold
5. deskew_image(binary) -> minAreaRect & rotation
6. remove_borders(binary) -> 10px margin removal
7. enhance_for_tesseract(binary) -> morphological closing

Tesseract invocation:
--oem 3 --psm 6 -l eng

Graceful error handling: Never crash, fallback cleanly.
Supports both legacy scan_vendor_bill and new scan_and_process_document.
"""

import os
import re
import io
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional, Tuple, List, Any

import numpy as np
import cv2
from PIL import Image
import pdfplumber

from app.schemas.invoice_schema import OCRExtractionResult, OCRFieldResult
from app.schemas.ocr_schema import ScanDocumentResponse, DocumentTypeEnum
from app.services.document_processor import process_document

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# OPENCV PREPROCESSING PIPELINE
# ─────────────────────────────────────────────

def load_image_from_bytes(file_bytes: bytes) -> Optional[np.ndarray]:
    """Decodes raw bytes into an OpenCV BGR image array."""
    try:
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        logger.warning(f"OpenCV failed to decode image bytes: {e}")
        return None


def convert_to_grayscale(img: np.ndarray) -> np.ndarray:
    """Converts 3-channel BGR image to grayscale."""
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def remove_noise(gray: np.ndarray) -> np.ndarray:
    """Removes salt-and-pepper noise via 3x3 median blur."""
    return cv2.medianBlur(gray, 3)


def apply_adaptive_threshold(gray: np.ndarray) -> np.ndarray:
    """Binarizes using Gaussian adaptive thresholding for varying illumination."""
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11,
        C=2
    )


def deskew_image(binary: np.ndarray) -> np.ndarray:
    """
    Detects skew angle of text lines using minimum area bounding rect
    and rotates back to horizontal.
    """
    try:
        coords = np.column_stack(np.where(binary < 128))
        if len(coords) < 50:
            return binary
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        
        if angle < -45:
            angle = -(90 + angle)
        elif angle > 45:
            angle = 90 - angle
        else:
            angle = -angle

        # If angle is negligible, do not warp
        if abs(angle) < 0.5 or abs(angle) > 45:
            return binary

        (h, w) = binary.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            binary, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        return rotated
    except Exception as e:
        logger.warning(f"Deskew failed, returning original: {e}")
        return binary


def remove_borders(binary: np.ndarray, margin: int = 10) -> np.ndarray:
    """Crops outer pixel borders to eliminate scanner edge artifacts."""
    h, w = binary.shape[:2]
    if h > 2 * margin and w > 2 * margin:
        return binary[margin:h - margin, margin:w - margin]
    return binary


def enhance_for_tesseract(binary: np.ndarray) -> np.ndarray:
    """Morphological closing to bridge character fragments."""
    kernel = np.ones((1, 1), np.uint8)
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


def preprocess_image_pipeline(file_bytes: bytes) -> Optional[np.ndarray]:
    """Runs the complete 7-step OpenCV preprocessing pipeline."""
    img = load_image_from_bytes(file_bytes)
    if img is None:
        return None
    gray = convert_to_grayscale(img)
    denoised = remove_noise(gray)
    binary = apply_adaptive_threshold(denoised)
    deskewed = deskew_image(binary)
    bordered = remove_borders(deskewed)
    enhanced = enhance_for_tesseract(bordered)
    return enhanced


# ─────────────────────────────────────────────
# REGEX PATTERNS (Indian Tax Invoices)
# ─────────────────────────────────────────────

GSTIN_PATTERN       = re.compile(r'\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b')
PAN_PATTERN         = re.compile(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b')
PHONE_PATTERN       = re.compile(r'(?:Ph|Phone|Tel|Mobile|Mob)[:\s.]*([6-9]\d{9})', re.IGNORECASE)
INV_NUM_PATTERN     = re.compile(
    r'(?:(?:Tax\s*)?Invoice\s*(?:No|Number|#)|Bill\s*(?:No|Number)|(?:\bINV[-/]))\s*[:.]*\s*([A-Z0-9/-]{3,30})',
    re.IGNORECASE
)
DATE_PATTERN        = re.compile(
    r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b',
    re.IGNORECASE
)
TOTAL_PATTERN       = re.compile(
    r'(?:Grand\s*Total|Total\s*Amount|Net\s*Amount|Amount\s*Payable|Total\s*Payable|(?<!Sub)\bTotal)[:\s]*'
    r'(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)',
    re.IGNORECASE
)
SUBTOTAL_PATTERN    = re.compile(
    r'(?:Sub[-\s]?Total|Taxable\s*(?:Value|Amount)|Basic\s*Amount)[:\s]*'
    r'(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)',
    re.IGNORECASE
)
CGST_PATTERN        = re.compile(r'CGST(?:\s*@\s*[\d.]+%)?[^0-9\n]*([\d,]+\.\d{2})', re.IGNORECASE)
SGST_PATTERN        = re.compile(r'SGST(?:\s*@\s*[\d.]+%)?[^0-9\n]*([\d,]+\.\d{2})', re.IGNORECASE)
IGST_PATTERN        = re.compile(r'IGST(?:\s*@\s*[\d.]+%)?[^0-9\n]*([\d,]+\.\d{2})', re.IGNORECASE)
DISCOUNT_PATTERN    = re.compile(r'(?:Discount|Disc\.?)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)', re.IGNORECASE)
DUE_DATE_PATTERN    = re.compile(r'(?:Due\s*Date|Payment\s*Due)[:\s]*([\d/-]+)', re.IGNORECASE)


def _clean_amount(raw: str) -> Optional[Decimal]:
    try:
        cleaned = re.sub(r'(?i)(Rs\.?|INR|₹)', '', raw)
        cleaned = re.sub(r'[,\s]', '', cleaned).strip()
        if cleaned:
            return Decimal(cleaned).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        pass
    return None


def _parse_date(raw: str) -> Optional[str]:
    formats = [
        '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y',
        '%d %b %Y', '%d %B %Y', '%B %d %Y', '%b %d %Y',
    ]
    raw = raw.strip()
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return raw


def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _extract_vendor_name(lines: List[str]) -> Optional[str]:
    candidates = []
    for line in lines[:8]:
        line = line.strip()
        if (len(line) > 3
                and not re.search(r'\d{6,}', line)
                and not re.search(r'GSTIN|PAN|GST|TAX INVOICE|INVOICE', line, re.IGNORECASE)):
            candidates.append(line)
    return candidates[0] if candidates else None


# ─────────────────────────────────────────────
# PRIMARY EXTRACTION ENGINES
# ─────────────────────────────────────────────

def _extract_text_pdfplumber(file_bytes: bytes, filename: str) -> Tuple[str, int]:
    text_parts = []
    page_count = 0
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
        logger.info(f"pdfplumber extracted {page_count} pages from {filename}")
    except Exception as e:
        logger.warning(f"pdfplumber failed for {filename}: {e}")
    return "\n".join(text_parts), page_count


def _extract_text_tesseract(file_bytes: bytes, filename: str) -> Tuple[str, int]:
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not available — skipping image OCR")
        return "", 0

    text_parts = []
    page_count = 0
    ext = os.path.splitext(filename.lower())[1]
    tess_config = '--oem 3 --psm 6 -l eng'

    try:
        if ext in ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'):
            # Run OpenCV preprocessing pipeline
            processed_cv = preprocess_image_pipeline(file_bytes)
            if processed_cv is not None:
                pil_img = Image.fromarray(processed_cv)
            else:
                pil_img = Image.open(io.BytesIO(file_bytes)).convert('RGB')
            
            try:
                text = pytesseract.image_to_string(pil_img, config=tess_config)
            except Exception:
                text = pytesseract.image_to_string(pil_img)
            text_parts.append(text)
            page_count = 1

        elif ext == '.pdf':
            try:
                from pdf2image import convert_from_bytes
                images = convert_from_bytes(file_bytes, dpi=200)
                page_count = len(images)
                for img in images:
                    # Convert PIL Image to BGR array for OpenCV pipeline
                    open_cv_image = np.array(img.convert('RGB'))[:, :, ::-1].copy()
                    gray = convert_to_grayscale(open_cv_image)
                    denoised = remove_noise(gray)
                    binary = apply_adaptive_threshold(denoised)
                    enhanced = enhance_for_tesseract(binary)
                    
                    try:
                        text = pytesseract.image_to_string(Image.fromarray(enhanced), config=tess_config)
                    except Exception:
                        text = pytesseract.image_to_string(img)
                    text_parts.append(text)
            except ImportError:
                logger.warning("pdf2image not available — cannot OCR scanned PDF pages")
        logger.info(f"Tesseract extracted {page_count} page(s) from {filename}")
    except Exception as e:
        logger.warning(f"Tesseract OCR failed for {filename}: {e}")

    return "\n".join(text_parts), page_count


def _run_regex_extraction(raw_text: str, warnings: list) -> OCRExtractionResult:
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    result = OCRExtractionResult()
    result.raw_text_preview = raw_text[:800]

    gstins = GSTIN_PATTERN.findall(raw_text)
    if gstins:
        result.vendor_gstin = OCRFieldResult(value=gstins[0], confidence=95.0, source="regex")
        if len(gstins) < 2:
            warnings.append("Only one GSTIN detected — could not distinguish buyer from seller GSTIN.")
    else:
        warnings.append("No GSTIN detected in document.")

    pan = _first_match(PAN_PATTERN, raw_text)
    if pan and len(pan) == 10:
        result.vendor_pan = OCRFieldResult(value=pan, confidence=85.0, source="regex")

    phone = _first_match(PHONE_PATTERN, raw_text)
    if phone:
        result.vendor_phone = OCRFieldResult(value=phone, confidence=80.0, source="regex")

    vendor_name = _extract_vendor_name(lines)
    if vendor_name:
        result.vendor_name = OCRFieldResult(value=vendor_name, confidence=60.0, source="heuristic")
    else:
        warnings.append("Could not reliably detect vendor name — please fill manually.")

    inv_num = _first_match(INV_NUM_PATTERN, raw_text)
    if inv_num:
        result.invoice_number = OCRFieldResult(value=inv_num.strip(), confidence=85.0, source="regex")
    else:
        warnings.append("Invoice number not detected. Please enter manually.")

    all_dates = DATE_PATTERN.findall(raw_text)
    due_date_raw = _first_match(DUE_DATE_PATTERN, raw_text)

    if all_dates:
        result.invoice_date = OCRFieldResult(value=_parse_date(all_dates[0]), confidence=75.0, source="regex")
    else:
        warnings.append("Invoice date not detected.")

    if due_date_raw:
        result.due_date = OCRFieldResult(value=_parse_date(due_date_raw), confidence=75.0, source="regex")
    elif len(all_dates) >= 2:
        result.due_date = OCRFieldResult(value=_parse_date(all_dates[1]), confidence=60.0, source="regex")

    total_raw = _first_match(TOTAL_PATTERN, raw_text)
    if total_raw:
        total = _clean_amount(total_raw)
        if total:
            result.total_amount = OCRFieldResult(value=str(total), confidence=90.0, source="regex")
    if not result.total_amount.value:
        warnings.append("Grand total not detected — please verify amount.")

    sub_raw = _first_match(SUBTOTAL_PATTERN, raw_text)
    if sub_raw:
        sub = _clean_amount(sub_raw)
        if sub:
            result.subtotal = OCRFieldResult(value=str(sub), confidence=85.0, source="regex")

    cgst_raw = _first_match(CGST_PATTERN, raw_text)
    if cgst_raw:
        cgst = _clean_amount(cgst_raw)
        if cgst:
            result.cgst_amount = OCRFieldResult(value=str(cgst), confidence=88.0, source="regex")

    sgst_raw = _first_match(SGST_PATTERN, raw_text)
    if sgst_raw:
        sgst = _clean_amount(sgst_raw)
        if sgst:
            result.sgst_amount = OCRFieldResult(value=str(sgst), confidence=88.0, source="regex")

    igst_raw = _first_match(IGST_PATTERN, raw_text)
    if igst_raw:
        igst = _clean_amount(igst_raw)
        if igst:
            result.igst_amount = OCRFieldResult(value=str(igst), confidence=88.0, source="regex")

    cgst_v = _clean_amount(result.cgst_amount.value or '0')
    sgst_v = _clean_amount(result.sgst_amount.value or '0')
    igst_v = _clean_amount(result.igst_amount.value or '0')
    computed_tax = (cgst_v or Decimal('0')) + (sgst_v or Decimal('0')) + (igst_v or Decimal('0'))
    if computed_tax > Decimal('0'):
        result.tax_amount = OCRFieldResult(value=str(computed_tax), confidence=85.0, source="computed")

    disc_raw = _first_match(DISCOUNT_PATTERN, raw_text)
    if disc_raw:
        disc = _clean_amount(disc_raw)
        if disc:
            result.discount_amount = OCRFieldResult(value=str(disc), confidence=75.0, source="regex")

    scored_fields = [
        result.vendor_gstin, result.vendor_name, result.invoice_number,
        result.invoice_date, result.total_amount, result.subtotal,
        result.cgst_amount, result.sgst_amount, result.igst_amount,
    ]
    detected = [f for f in scored_fields if f.value]
    result.overall_confidence = round(
        (sum(f.confidence for f in detected) / len(scored_fields)) if scored_fields else 0.0,
        2
    )
    result.extraction_warnings = warnings
    return result


# ─────────────────────────────────────────────
# PUBLIC INTERFACES
# ─────────────────────────────────────────────

def scan_vendor_bill(
    file_bytes: bytes,
    filename: str,
) -> OCRExtractionResult:
    """
    Legacy entry point for bill scanning.
    Tries pdfplumber first (digital PDFs), falls back to Tesseract for images/scans.
    Returns OCRExtractionResult.
    """
    warnings: List[str] = []
    ext = os.path.splitext(filename.lower())[1]

    raw_text = ""
    page_count = 0

    if ext == '.pdf':
        raw_text, page_count = _extract_text_pdfplumber(file_bytes, filename)
        engine = "pdfplumber"

        if len(raw_text.strip()) < 50:
            warnings.append("PDF appears to be image-based (no embedded text). Falling back to Tesseract OCR.")
            raw_text, page_count = _extract_text_tesseract(file_bytes, filename)
            engine = "pdfplumber+tesseract"
    elif ext in ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'):
        raw_text, page_count = _extract_text_tesseract(file_bytes, filename)
        engine = "opencv+tesseract"
    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: PDF, JPG, JPEG, PNG, TIFF, BMP."
        )

    if not raw_text.strip():
        warnings.append("No text could be extracted from the document. Please enter details manually.")
        result = OCRExtractionResult()
        result.extraction_warnings = warnings
        result.page_count = page_count
        result.extraction_engine = engine
        return result

    result = _run_regex_extraction(raw_text, warnings)
    result.page_count = page_count
    result.extraction_engine = engine
    return result


def scan_and_process_document(
    file_bytes: bytes,
    filename: str,
) -> ScanDocumentResponse:
    """
    Phase 6 Unified Entry Point for Document Scanner.
    Extracts raw text (OpenCV + Tesseract or pdfplumber), runs 2-stage classifier,
    extracts structured fields, and returns a non-persisted preview.
    """
    ext = os.path.splitext(filename.lower())[1]
    raw_text = ""
    page_count = 1
    engine = "opencv+tesseract"

    try:
        if ext == '.pdf':
            raw_text, page_count = _extract_text_pdfplumber(file_bytes, filename)
            engine = "pdfplumber"
            if len(raw_text.strip()) < 50:
                raw_text, page_count = _extract_text_tesseract(file_bytes, filename)
                engine = "pdfplumber+tesseract"
        elif ext in ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'):
            raw_text, page_count = _extract_text_tesseract(file_bytes, filename)
            engine = "opencv+tesseract"
        else:
            raise ValueError(f"Unsupported file type '{ext}'.")

        response = process_document(raw_text, page_count=page_count, engine=engine)
        return response

    except Exception as e:
        logger.warning(f"Document scan & process failed: {e}")
        return ScanDocumentResponse(
            document_type=DocumentTypeEnum.UNKNOWN,
            type_confidence=0.0,
            overall_confidence=0.0,
            fields={},
            raw_text_preview="",
            suggested_action="Review Document",
            warnings=[f"Scan processing error: {str(e)}"],
            page_count=page_count,
            engine=engine
        )
