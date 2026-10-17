"""
Logging Configuration — Structured, Privacy-Aware Logging
Configures logging without leaking personal data.
"""

import logging
import sys
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from contextvars import ContextVar

from config import settings


# Context variable for request ID (thread-safe)
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class PrivacyAwareFormatter(logging.Formatter):
    """
    Custom formatter that includes request ID and prevents PII leakage.
    Never logs resume content, emails, phones, or full file paths.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Add request ID if available
        request_id = request_id_var.get()
        if request_id:
            record.request_id = request_id
        else:
            record.request_id = "-"

        # Add timestamp
        record.timestamp = datetime.now(timezone.utc).isoformat()

        return super().format(record)


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    Useful for log aggregation systems (ELK, CloudWatch, etc.)
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get() or "-",
        }

        # Add exception info if present (but sanitize it)
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (excluding sensitive ones)
        sensitive_fields = {"password", "token", "secret", "resume_text", "email", "phone"}
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "request_id", "timestamp",
            }:
                if key.lower() in sensitive_fields:
                    log_data[key] = "[REDACTED]"
                else:
                    try:
                        json.dumps(value)  # Check if serializable
                        log_data[key] = value
                    except (TypeError, ValueError):
                        log_data[key] = str(value)

        return json.dumps(log_data)


def setup_logging():
    """
    Configure application logging.

    - Development: Human-readable format
    - Production: JSON format for log aggregation
    - Suppresses noisy third-party loggers
    """
    # Determine log level
    log_level = logging.DEBUG if settings.debug else logging.INFO

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)

    # Choose formatter based on environment
    if settings.environment == "production":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            PrivacyAwareFormatter(
                "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(console_handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)
    logging.getLogger("fitz").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(name)


def set_request_id(request_id: str = None) -> str:
    """
    Set request ID for the current context.
    If not provided, generates a new one.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    request_id_var.set(request_id)
    return request_id


def get_request_id() -> Optional[str]:
    """Get the current request ID."""
    return request_id_var.get()


def sanitize_error_message(error: Exception, include_details: bool = False) -> str:
    """
    Sanitize an exception message for logging or client response.

    Args:
        error: Exception object
        include_details: Whether to include technical details (development only)

    Returns:
        Safe error message string
    """
    error_type = type(error).__name__

    if settings.debug and include_details:
        return f"{error_type}: {str(error)[:200]}"

    # In production, return generic messages
    # Map common exceptions to user-friendly messages
    error_messages = {
        "FileNotFoundError": "Requested resource not found",
        "PermissionError": "Permission denied",
        "ValueError": "Invalid input provided",
        "KeyError": "Missing required data",
        "TimeoutError": "Operation timed out",
        "ConnectionError": "Service temporarily unavailable",
        "HTTPException": "Request failed",
    }

    return error_messages.get(error_type, "An internal error occurred")


# Initialize logging on module import
setup_logging()
