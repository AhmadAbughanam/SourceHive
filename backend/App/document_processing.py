"""
Document inspection and extraction utilities shared between the FastAPI API
and the legacy Streamlit prototype.

This module auto-detects document kind, runs OCR for image-based resumes,
and normalizes the extracted text for downstream parsing.
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Dict, Optional

from PyPDF2 import PdfReader  # type: ignore

try:
    import fitz  # PyMuPDF type: ignore
except Exception:  # pragma: no cover - optional dependency
    fitz = None

try:
    from PIL import Image, ImageOps  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Image = None
    ImageOps = None

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None

try:
    from docx import Document  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Document = None


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
TEXT_EXTS = {".txt", ".rtf"}
DOCX_EXTS = {".docx"}
TEXT_CHAR_THRESHOLD_PER_DOC = 200
TEXT_CHAR_THRESHOLD_PER_PAGE = 30


def guess_mime_from_bytes(file_bytes: bytes, ext: str = "") -> str:
    """Return a best-effort mime guess using file signatures."""
    if file_bytes.startswith(b"%PDF"):
        return "application/pdf"
    if file_bytes.startswith(b"PK\x03\x04"):
        if ext == ".docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return "application/zip"
    if file_bytes.startswith(b"\xD0\xCF\x11\xE0"):
        return "application/msword"
    if file_bytes[:3] == b"\xFF\xD8\xFF":
        return "image/jpeg"
    if file_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if file_bytes[:4] in (b"RIFF", b"WEBP"):
        return "image/webp"
    if file_bytes[:2] == b"BM":
        return "image/bmp"
    if ext in TEXT_EXTS:
        return "text/plain"
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def normalize_extracted_text(text: str) -> str:
    """Normalize whitespace/junk in extracted text."""
    if not text:
        return ""
    text = text.replace("\r", "\n")
    text = re.sub(r"-\n", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def analyze_pdf(file_path: str) -> Dict[str, object]:
    """Inspect a PDF to determine whether OCR is needed."""
    doc_info: Dict[str, object] = {
        "kind": "unknown_pdf",
        "page_count": 0,
        "text_char_count": 0,
        "page_text_lengths": [],
        "has_images": False,
        "error": None,
    }
    try:
        if fitz:
            pdf = fitz.open(file_path)
            doc_info["page_count"] = pdf.page_count
            lengths = []
            for page in pdf:
                text = page.get_text("text") or ""
                length = len(text.strip())
                lengths.append(length)
                doc_info["text_char_count"] += length
                if page.get_images(full=True):
                    doc_info["has_images"] = True
            pdf.close()
            doc_info["page_text_lengths"] = lengths
        else:
            with open(file_path, "rb") as fh:
                reader = PdfReader(fh)
                doc_info["page_count"] = len(reader.pages)
                lengths = []
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    length = len(page_text.strip())
                    lengths.append(length)
                    doc_info["text_char_count"] += length
                doc_info["page_text_lengths"] = lengths
    except Exception as exc:  # pragma: no cover - inspection best-effort
        doc_info["error"] = str(exc)
        return doc_info

    text_chars = doc_info["text_char_count"]
    per_page_hits = [
        length for length in doc_info.get("page_text_lengths", []) if length >= TEXT_CHAR_THRESHOLD_PER_PAGE
    ]
    if text_chars >= TEXT_CHAR_THRESHOLD_PER_DOC or per_page_hits:
        doc_info["kind"] = "text_pdf"
    elif doc_info.get("has_images"):
        doc_info["kind"] = "image_pdf"
    else:
        doc_info["kind"] = "unknown_pdf"
    return doc_info


def extract_pdf_text(file_path: str) -> str:
    """Return plain text from a text-based PDF."""
    chunks = []
    if fitz:
        doc = fitz.open(file_path)
        for page in doc:
            chunks.append(page.get_text("text") or "")
        doc.close()
    else:
        with open(file_path, "rb") as fh:
            reader = PdfReader(fh)
            for page in reader.pages:
                chunks.append(page.extract_text() or "")
    return normalize_extracted_text("\n".join(chunks))


def _ensure_ocr_dependencies():
    if not pytesseract or not Image:
        raise RuntimeError(
            "OCR dependencies are missing. Install Pillow + pytesseract and the system tesseract binary."
        )


def extract_pdf_ocr(file_path: str) -> str:
    """Run OCR on a PDF (per page) when no embedded text exists."""
    if not fitz:
        raise RuntimeError("PyMuPDF is required for PDF OCR but is not installed.")
    _ensure_ocr_dependencies()
    doc = fitz.open(file_path)
    ocr_chunks = []
    for page in doc:
        try:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img = img.convert("RGB")
            ocr_chunks.append(pytesseract.image_to_string(img, config="--oem 3 --psm 6"))
        except Exception as exc:  # pragma: no cover - OCR best-effort
            ocr_chunks.append(f"[OCR failed: {exc}]")
    doc.close()
    return normalize_extracted_text("\n".join(ocr_chunks))


def extract_image_ocr(file_path: str) -> str:
    """OCR extraction for raw image resumes."""
    _ensure_ocr_dependencies()
    img = Image.open(file_path).convert("RGB")
    if ImageOps:
        img = ImageOps.grayscale(img)
    return normalize_extracted_text(pytesseract.image_to_string(img, config="--oem 3 --psm 6"))


def extract_docx_text(file_path: str) -> str:
    if not Document:
        raise RuntimeError("python-docx is required to parse DOCX files.")
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    return normalize_extracted_text("\n".join(paragraphs))


def extract_txt_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
        return normalize_extracted_text(fh.read())


def detect_document_kind(file_path: str, original_name: Optional[str], header_bytes: bytes) -> Dict[str, object]:
    """Return document metadata so we know whether OCR is needed."""
    ext = os.path.splitext(original_name or file_path or "")[1].lower()
    mime_guess = guess_mime_from_bytes(header_bytes, ext)
    info: Dict[str, object] = {
        "kind": "unknown",
        "mime_guess": mime_guess,
        "page_count": None,
        "text_char_count": None,
        "has_images": False,
        "error": None,
        "extension": ext,
    }

    if mime_guess == "application/pdf":
        pdf_stats = analyze_pdf(file_path)
        info.update(pdf_stats)
        return info
    if ext in DOCX_EXTS or mime_guess.startswith("application/vnd"):
        info["kind"] = "docx"
        return info
    if ext in TEXT_EXTS or mime_guess.startswith("text/"):
        info["kind"] = "txt"
        return info
    if ext in IMAGE_EXTS or mime_guess.startswith("image/"):
        info["kind"] = "image"
        return info
    return info


def extract_document_text(file_path: str, doc_info: Dict[str, object]) -> Dict[str, object]:
    """Extract text according to the detected document kind."""
    kind = doc_info.get("kind") or "unknown"
    response = {
        "text": "",
        "method": None,
        "ocr_used": False,
        "error": None,
    }
    try:
        if kind == "text_pdf":
            response["text"] = extract_pdf_text(file_path)
            response["method"] = "text_extract"
        elif kind == "image_pdf":
            response["text"] = extract_pdf_ocr(file_path)
            response["method"] = "ocr"
            response["ocr_used"] = True
        elif kind == "image":
            response["text"] = extract_image_ocr(file_path)
            response["method"] = "ocr"
            response["ocr_used"] = True
        elif kind == "docx":
            response["text"] = extract_docx_text(file_path)
            response["method"] = "docx_parser"
        elif kind == "txt":
            response["text"] = extract_txt_text(file_path)
            response["method"] = "text_file"
        else:
            ext = (doc_info.get("extension") or "").lower()
            if ext in TEXT_EXTS:
                response["text"] = extract_txt_text(file_path)
                response["method"] = "text_file"
            else:
                response["text"] = extract_pdf_text(file_path)
                response["method"] = "text_extract"
    except Exception as exc:  # pragma: no cover - we surface the error
        response["error"] = str(exc)
    response["text"] = normalize_extracted_text(response.get("text") or "")
    return response


def analyze_and_extract(
    file_path: str,
    *,
    original_name: Optional[str] = None,
    header_bytes: Optional[bytes] = None,
) -> Dict[str, object]:
    """High-level helper to inspect a document then extract its text."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume path not found: {file_path}")
    if header_bytes is None:
        with open(path, "rb") as fh:
            header_bytes = fh.read(8192)
    detection = detect_document_kind(str(path), original_name or path.name, header_bytes or b"")
    extraction = extract_document_text(str(path), detection)
    return {
        "doc_kind": detection.get("kind"),
        "file_mime": detection.get("mime_guess"),
        "ocr_used": extraction.get("ocr_used", False),
        "extraction_method": extraction.get("method"),
        "extraction_error": extraction.get("error") or detection.get("error"),
        "text": extraction.get("text"),
        "text_length": len(extraction.get("text") or ""),
        "details": detection,
    }


def run_cv_understanding(
    file_path: str,
    *,
    original_name: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
) -> Dict[str, object]:
    """
    Backwards-compatible helper that mirrors the Streamlit prototype.

    Args:
        file_path: absolute or relative path to the saved document.
        original_name: original filename from the upload (optional).
        file_bytes: optional byte buffer (used to avoid re-reading headers).

    Returns:
        Same payload as analyze_and_extract (doc_kind, text, metadata, etc.).
    """
    header = file_bytes[:8192] if file_bytes else None
    return analyze_and_extract(
        file_path,
        original_name=original_name,
        header_bytes=header,
    )


def redact_preview_text(text: str, limit: int = 500) -> str:
    """Return a redacted preview of the extracted text for UI consumption."""
    if not text:
        return ""
    redacted = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted email]", text)
    redacted = re.sub(r"\+?\d[\d\-\s\(\)]{6,}\d", "[redacted phone]", redacted)
    snippet = redacted[:limit]
    if len(redacted) > limit:
        snippet += "..."
    return snippet
