"""
Secure PDF Validator — Upload Security
Validates PDF uploads for security and correctness.
Prevents malicious files, DoS, and resource exhaustion.
"""

import fitz  # PyMuPDF
from typing import Tuple, Optional, List
from fastapi import UploadFile, HTTPException

from config import settings

# python-magic is optional — it requires libmagic on the host system.
# If unavailable we fall back to signature-based validation only.
try:
    import magic
    _HAS_MAGIC = True
except (ImportError, OSError):
    magic = None
    _HAS_MAGIC = False


# PDF magic bytes signatures
PDF_SIGNATURES = [
    b'%PDF-1.4',
    b'%PDF-1.5',
    b'%PDF-1.6',
    b'%PDF-1.7',
    b'%PDF-2.0',
]


class PDFValidator:
    """Validates PDF files for security and correctness."""

    def __init__(
        self,
        max_size_bytes: int = None,
        max_pages: int = None,
        allowed_extensions: List[str] = None,
    ):
        self.max_size_bytes = max_size_bytes or settings.max_file_size_bytes
        self.max_pages = max_pages or settings.max_pdf_pages
        self.allowed_extensions = allowed_extensions or [".pdf"]

    def validate_file(self, file: UploadFile, content: bytes) -> Tuple[bool, Optional[str]]:
        """
        Validate a single uploaded file.

        Args:
            file: FastAPI UploadFile object
            content: File content bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file extension
        if not self._validate_extension(file.filename):
            return False, f"Invalid file extension. Allowed: {', '.join(self.allowed_extensions)}"

        # Check file size
        if len(content) > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            return False, f"File too large. Maximum size: {max_mb:.1f}MB"

        # Check minimum size (empty or near-empty file)
        if len(content) < 100:
            return False, "File is too small or empty"

        # Check MIME type
        if not self._validate_mime_type(content):
            return False, "Invalid file type. Expected PDF"

        # Check PDF signature
        if not self._validate_pdf_signature(content):
            return False, "Invalid PDF file signature"

        # Check PDF structure and page count
        pdf_error = self._validate_pdf_structure(content)
        if pdf_error:
            return False, pdf_error

        return True, None

    def _validate_extension(self, filename: str) -> bool:
        """Check if file has allowed extension."""
        if not filename:
            return False

        ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        return ext in self.allowed_extensions

    def _validate_mime_type(self, content: bytes) -> bool:
        """Check actual MIME type using magic bytes."""
        if not _HAS_MAGIC:
            # python-magic unavailable — signature check still applies
            return True
        try:
            mime = magic.from_buffer(content[:1024], mime=True)
            return mime == 'application/pdf'
        except Exception:
            # If magic detection fails, rely on PDF signature check
            return True

    def _validate_pdf_signature(self, content: bytes) -> bool:
        """Check PDF file signature/magic bytes."""
        # PDF files start with %PDF-
        if not content.startswith(b'%PDF-'):
            return False

        # Check against known signatures
        for sig in PDF_SIGNATURES:
            if content.startswith(sig):
                return True

        # Allow other PDF versions (e.g., %PDF-1.3)
        return True

    def _validate_pdf_structure(self, content: bytes) -> Optional[str]:
        """
        Validate PDF structure, check for encryption, and page count.

        Returns:
            Error message string or None if valid
        """
        try:
            doc = fitz.open(stream=content, filetype="pdf")

            # Check if encrypted
            if doc.is_encrypted:
                doc.close()
                return "PDF is encrypted and cannot be processed"

            # Check page count
            page_count = len(doc)
            if page_count == 0:
                doc.close()
                return "PDF has no pages"

            if page_count > self.max_pages:
                doc.close()
                return f"PDF has too many pages ({page_count}). Maximum: {self.max_pages}"

            # Check for malformed PDF (PyMuPDF will raise if severely corrupted)
            # Try to access first page
            if page_count > 0:
                try:
                    _ = doc[0].get_text("text")
                except Exception as e:
                    doc.close()
                    return f"PDF appears to be malformed or corrupted"

            doc.close()
            return None

        except Exception as e:
            return f"Invalid or corrupted PDF: {str(e)[:100]}"

    def validate_batch(self, files: List[UploadFile]) -> Tuple[List[Tuple[UploadFile, bytes]], List[dict]]:
        """
        Validate a batch of files.

        Args:
            files: List of UploadFile objects

        Returns:
            Tuple of (valid_files, errors)
            valid_files: List of (file, content) tuples
            errors: List of error dicts with filename and error
        """
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        # Check batch size
        if len(files) > settings.max_batch_size:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files. Maximum: {settings.max_batch_size}"
            )

        valid_files = []
        errors = []

        for file in files:
            try:
                content = file.file.read()
                is_valid, error_msg = self.validate_file(file, content)

                if is_valid:
                    valid_files.append((file, content))
                else:
                    errors.append({
                        "filename": file.filename or "unknown",
                        "error": error_msg
                    })
            except Exception as e:
                errors.append({
                    "filename": file.filename or "unknown",
                    "error": f"Failed to read file: {str(e)[:100]}"
                })

        return valid_files, errors


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe storage.
    Removes path traversal attempts and special characters.

    Args:
        filename: Original filename

    Returns:
        Safe filename
    """
    import re
    from datetime import datetime
    import uuid

    if not filename:
        return f"resume_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.pdf"

    # Remove path components (prevent path traversal)
    filename = filename.split('/')[-1].split('\\')[-1]

    # Remove or replace dangerous characters
    # Keep only alphanumeric, dash, underscore, dot
    safe_name = re.sub(r'[^\w\-\.]', '_', filename)

    # Prevent double extensions
    if safe_name.count('.') > 1:
        parts = safe_name.rsplit('.', 1)
        safe_name = parts[0].replace('.', '_') + '.' + parts[1]

    # Ensure .pdf extension
    if not safe_name.lower().endswith('.pdf'):
        safe_name += '.pdf'

    # Limit length
    if len(safe_name) > 200:
        name_part = safe_name[:-4][:196]
        safe_name = name_part + '.pdf'

    return safe_name


# Global validator instance
pdf_validator = PDFValidator()
