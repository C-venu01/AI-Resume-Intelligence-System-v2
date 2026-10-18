"""
Configuration Module — Environment Variables and Settings
Centralized configuration with validation and sensible defaults.
"""

import os
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All settings have sensible defaults for development.
    """

    # ==================== APPLICATION ====================
    app_name: str = "AI Resume Intelligence System"
    app_version: str = "2.0.0"
    environment: str = "development"  # development | staging | production
    debug: bool = False

    # ==================== SERVER ====================
    host: str = "0.0.0.0"
    port: int = 8000

    # ==================== DATABASE ====================
    # Use /app/backend/data directory for Docker persistence
    # Defaults to local directory for development
    database_path: Optional[str] = None

    @property
    def resolved_database_path(self) -> str:
        """Resolve the actual database path to use."""
        if self.database_path:
            return self.database_path

        # Check if we're in a Docker container (common pattern)
        if os.path.exists("/app/backend"):
            return "/app/backend/data/resume_db.sqlite"

        # Development fallback
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(backend_dir, "resume_db.sqlite")

    # ==================== AUTHENTICATION ====================
    jwt_secret_key: str = ""  # MUST be set in production
    jwt_expiration_hours: int = 24
    admin_username: str = "admin"
    admin_password_hash: str = ""  # MUST be set in production
    admin_password: str = ""

    # ==================== CORS ====================
    # Comma-separated list of allowed origins
    cors_origins: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if not self.cors_origins:
            # Development default - allow localhost
            if self.environment == "development":
                return [
                    "http://localhost:3000",
                    "http://localhost:8000",
                    "http://127.0.0.1:3000",
                    "http://127.0.0.1:8000",
                ]
            return []

        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ==================== FILE UPLOAD ====================
    max_file_size_mb: int = 10  # Max individual file size
    max_batch_size: int = 20  # Max files per upload
    max_pdf_pages: int = 50  # Max pages per PDF
    allowed_extensions: str = ".pdf"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    # ==================== RATE LIMITING ====================
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100  # Requests per minute
    rate_limit_upload_requests: int = 10  # Upload requests per minute
    rate_limit_match_requests: int = 20  # Job match requests per minute

    # ==================== SECURITY ====================
    trusted_proxies: str = ""  # Comma-separated list of trusted proxy IPs

    @property
    def trusted_proxies_list(self) -> List[str]:
        if not self.trusted_proxies:
            return []
        return [ip.strip() for ip in self.trusted_proxies.split(",") if ip.strip()]

    # ==================== MONITORING ====================
    prometheus_enabled: bool = True

    # ==================== MODEL ====================
    # sentence-transformers model to use
    embedding_model: str = "all-MiniLM-L6-v2"

    # ==================== VALIDATION ====================

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    def validate_production_settings(self) -> List[str]:
        """
        Validate that all required production settings are set.
        Returns list of missing/invalid settings.
        """
        issues = []

        if self.environment == "production":
            if not self.jwt_secret_key:
                issues.append("JWT_SECRET_KEY must be set in production")

            if not (self.admin_password_hash or self.admin_password):
                issues.append(
                    "ADMIN_PASSWORD_HASH or ADMIN_PASSWORD must be set in production"
                )

            if not self.cors_origins:
                issues.append("CORS_ORIGINS must be set in production (explicit allowed origins)")

            if "dev-key" in self.jwt_secret_key:
                issues.append("JWT_SECRET_KEY appears to be a development key")

        return issues

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Print configuration summary on import (only in development)
if settings.environment == "development":
    print(f"[Config] Environment: {settings.environment}")
    print(f"[Config] Database: {settings.resolved_database_path}")
    print(f"[Config] CORS Origins: {settings.cors_origins_list}")
    print(f"[Config] Max File Size: {settings.max_file_size_mb}MB")
    print(f"[Config] Rate Limiting: {'Enabled' if settings.rate_limit_enabled else 'Disabled'}")
