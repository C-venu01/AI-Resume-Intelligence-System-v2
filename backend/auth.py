"""
Authentication & Authorization Module
JWT-based authentication with secure password hashing.
Protects sensitive candidate data and destructive operations.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
import jwt

# ==================== CONFIGURATION ====================

# Secret key for JWT signing - MUST be set via environment variable in production
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY:
    # Generate a random key for development (NOT for production)
    JWT_SECRET_KEY = "dev-key-" + secrets.token_urlsafe(32)
    print("[Auth] WARNING: Using development JWT key. Set JWT_SECRET_KEY environment variable for production!")

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# Admin credentials - MUST be set via environment variables in production
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer scheme for token extraction
security = HTTPBearer(auto_error=False)


# ==================== INITIALIZATION ====================

def _init_admin_credentials():
    """
    Initialize admin credentials.
    In production, password hash should be set via ADMIN_PASSWORD_HASH env var.
    For development, we hash the default password.
    """
    global ADMIN_PASSWORD_HASH

    if not ADMIN_PASSWORD_HASH:
        # Development fallback: hash a default password
        default_password = "admin123"
        ADMIN_PASSWORD_HASH = pwd_context.hash(default_password)
        print(f"[Auth] WARNING: Using default admin password '{default_password}'. Set ADMIN_PASSWORD_HASH for production!")

    # Validate that we have required config
    if os.getenv("ENVIRONMENT", "development") == "production":
        if not os.getenv("JWT_SECRET_KEY"):
            raise RuntimeError("JWT_SECRET_KEY must be set in production environment!")
        if not os.getenv("ADMIN_PASSWORD_HASH"):
            raise RuntimeError("ADMIN_PASSWORD_HASH must be set in production environment!")


# Initialize on module import
_init_admin_credentials()


# ==================== PASSWORD UTILITIES ====================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ==================== JWT UTILITIES ====================

def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload to encode in the token (e.g., {"sub": "admin"})
        expires_delta: Custom expiration time

    Returns:
        Encoded JWT string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict]:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT string

    Returns:
        Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ==================== AUTHENTICATION DEPENDENCIES ====================

def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """
    FastAPI dependency that requires valid authentication.
    Use this to protect endpoints.

    Usage:
        @app.get("/protected")
        async def protected_route(user: dict = Depends(require_auth)):
            return {"user": user}

    Returns:
        User payload from JWT token

    Raises:
        HTTPException: 401 if not authenticated
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def optional_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[Dict]:
    """
    FastAPI dependency for optional authentication.
    Returns None if not authenticated, otherwise returns user payload.

    Useful for endpoints that behave differently for authenticated vs anonymous users.
    """
    if not credentials:
        return None

    token = credentials.credentials
    return decode_access_token(token)


# ==================== ROLE-BASED AUTHORIZATION ====================

def require_role(role: str):
    """
    Decorator factory for role-based access control.

    Usage:
        @app.delete("/dangerous")
        async def dangerous_operation(user: dict = Depends(require_role("admin"))):
            ...
    """
    def role_checker(user: Dict = Depends(require_auth)) -> Dict:
        user_role = user.get("role", "")
        if user_role != role:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required role: {role}",
            )
        return user

    return role_checker


# ==================== LOGIN/LOGOUT LOGIC ====================

def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """
    Authenticate a user by username and password.

    Args:
        username: Username to authenticate
        password: Plain password to verify

    Returns:
        User info dict if authenticated, None otherwise
    """
    # For this application, we only have an admin user
    if username != ADMIN_USERNAME:
        return None

    if not verify_password(password, ADMIN_PASSWORD_HASH):
        return None

    return {
        "sub": username,
        "role": "admin",
        "name": "Administrator",
    }


def login(username: str, password: str) -> Optional[Dict]:
    """
    Perform login and return access token.

    Args:
        username: Username
        password: Password

    Returns:
        Dict with access_token and token_type, or None if auth failed
    """
    user = authenticate_user(username, password)

    if not user:
        return None

    access_token = create_access_token(data=user)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRATION_HOURS * 3600,  # seconds
        "user": {
            "username": user["sub"],
            "role": user["role"],
        }
    }


# ==================== SECURITY HEADERS MIDDLEWARE ====================

async def add_security_headers(request: Request, call_next):
    """
    FastAPI middleware to add security headers to all responses.
    """
    response = await call_next(request)

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # XSS protection (legacy browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Content Security Policy - allow inline scripts/styles for simplicity
    # In production, consider stricter CSP with nonces or hashes
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
    )

    # HSTS - only add in production with HTTPS
    if os.getenv("ENVIRONMENT") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# ==================== UTILITY FUNCTIONS ====================

def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_password_hash_command(password: str) -> str:
    """
    Generate a password hash for setting ADMIN_PASSWORD_HASH.
    Useful for setup scripts.

    Usage:
        python -c "from auth import generate_password_hash_command; print(generate_password_hash_command('my-secure-password'))"
    """
    return hash_password(password)


# ==================== CLI UTILITY ====================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "hash-password":
        if len(sys.argv) < 3:
            print("Usage: python auth.py hash-password <password>")
            sys.exit(1)

        password = sys.argv[2]
        hashed = hash_password(password)
        print(f"Password hash: {hashed}")
        print(f"\nSet this as ADMIN_PASSWORD_HASH environment variable.")
    else:
        print("Auth module - JWT authentication for AI Resume Intelligence System")
        print("Commands:")
        print("  python auth.py hash-password <password>  - Generate password hash")
