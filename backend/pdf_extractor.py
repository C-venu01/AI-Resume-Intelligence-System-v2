"""
PDF Text Extractor — PyMuPDF-based
Extracts clean text from resume PDFs with multi-column support.
"""

import fitz  # PyMuPDF
import re
from typing import Optional


def extract_text_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """
    Extract text from PDF bytes using PyMuPDF.
    
    Args:
        pdf_bytes: Raw bytes of the PDF file.
    
    Returns:
        Cleaned text string, or None if extraction fails.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""

        for page in doc:
            # Extract text with layout preservation (handles multi-column)
            text = page.get_text("text")
            if text:
                full_text += text + "\n"

        doc.close()

        # Clean the extracted text
        cleaned = _clean_text(full_text)

        # Minimum length check — skip near-empty PDFs
        if len(cleaned) < 50:
            return None

        return cleaned

    except Exception as e:
        print(f"[PDF Extractor] Error: {e}")
        return None


def _clean_text(text: str) -> str:
    """
    Clean and normalize extracted PDF text.
    
    - Remove excessive whitespace
    - Fix common encoding issues
    - Normalize line breaks
    """
    # Replace multiple spaces with single space
    text = re.sub(r'[ \t]+', ' ', text)

    # Replace 3+ newlines with 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Fix common encoding artifacts
    replacements = {
        '\u2019': "'",   # Right single quote
        '\u2018': "'",   # Left single quote
        '\u201c': '"',   # Left double quote
        '\u201d': '"',   # Right double quote
        '\u2013': '-',   # En dash
        '\u2014': '-',   # Em dash
        '\u2022': '•',   # Bullet
        '\uf0b7': '•',   # Another bullet variant
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Remove null bytes and other control characters (keep newlines/tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    return text.strip()


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Get the number of pages in a PDF."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0
