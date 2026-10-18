#!/usr/bin/env python3
"""Generate production credentials for deployment."""

import secrets
import bcrypt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

print("=" * 70)
print("GENERATING PRODUCTION CREDENTIALS")
print("=" * 70)

# Generate secure JWT secret key (cryptographically random)
jwt_secret = secrets.token_urlsafe(64)
print("\n[JWT_SECRET_KEY]")
print(jwt_secret)
print("\nCopy this into your environment variables:")
print(f"JWT_SECRET_KEY={jwt_secret}")

# Generate password hash
plain_password = secrets.token_urlsafe(24)
password_hash = pwd_context.hash(plain_password)

print("\n[ADMIN_PASSWORD_HASH]")
print(password_hash)
print(f"\nGenerated admin password: {plain_password}")

print("\n" + "=" * 70)
print("DEPLOYMENT CONFIGURATION")
print("=" * 70)

default_cors = "https://ai-resume-intelligence-system-v2.vercel.app"
print(f"\n[CORS_ORIGINS]")
print(default_cors)
print(f"In production, add your actual URL(s): {default_cors}")

print("\n[DATABASE]")
print("VOLUME: Server will mount /tmp/resume_db.sqlite automatically")

print("\n[MONITORING]")
print("PROMETHEUS_ENABLED=false (default in cloud)")

print("\n" + "=" * 70)
print("RECOMMENDED VOLUME FOR DATABASE PERSISTENCE")
print("=" * 70)
print("""
If using Render.com or similar with file system:
1. Set DATABASE_PATH=/tmp/resume_db.sqlite (already configured)
2. On startup, copy database to mounted volume:
   mkdir -p /tmp/data && cp /tmp/resume_db.sqlite /tmp/data/resume_db.sqlite
3. Or use environment like: DATABASE_PATH=/tmp/data/resume_db.sqlite
""")

print("\n[REQUIREMENTS]")
print("- JWT_SECRET_KEY must be set (above)")
print("- ADMIN_PASSWORD_HASH must be set (above)")
print("- CORS_ORIGINS must include all frontend domains")
print("- ENVIRONMENT=production")