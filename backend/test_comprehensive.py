"""
AI Resume Intelligence System 2.0 — Comprehensive Security & API Tests
Tests authentication, authorization, rate limiting, file validation, and all API endpoints.
"""

import os
import sys
import json
import io
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
import asyncio

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(__file__))

from pdf_extractor import extract_text_from_pdf, get_pdf_page_count
from resume_analyzer import analyze_resume
from database import (
    init_db, save_candidate, get_all_candidates, get_candidate,
    delete_candidate, delete_all_candidates, save_job_description,
    get_job_descriptions, save_match_result, get_stats,
    set_db_path, count_candidates,
)
from models import JobMatchRequest, CandidateResponse, LoginRequest
from auth import (
    hash_password, verify_password, create_access_token,
    decode_access_token, login, authenticate_user,
)
from validators import pdf_validator, sanitize_filename
from rate_limiter import InMemoryRateLimiter


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Use a temp database for every test so tests don't interfere."""
    db_path = str(tmp_path / "test_resume.sqlite")
    monkeypatch.setattr("database.DB_PATH", db_path)
    set_db_path(db_path)
    init_db()
    yield db_path


@pytest.fixture
def client():
    """FastAPI TestClient (imports app fresh so DB patch is active)."""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_token():
    """Generate a valid auth token for testing."""
    token = create_access_token(data={"sub": "testadmin", "role": "admin"})
    return token


@pytest.fixture
def auth_headers(auth_token):
    """Return authorization headers with valid token."""
    return {"Authorization": f"Bearer {auth_token}"}


def _make_minimal_pdf(text: str = "John Doe\njohn@email.com\nPython Developer") -> bytes:
    """Create a minimal valid PDF with the given text using PyMuPDF."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _sample_candidate(overrides: dict = None) -> dict:
    """Return a complete candidate dict ready for save_candidate()."""
    data = {
        "candidate_name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "+1-555-0100",
        "linkedin": "",
        "experience_years": 3,
        "experience_level": "Mid-level",
        "specialization": "Backend Developer",
        "technologies": ["Python", "FastAPI", "Docker"],
        "certifications": ["AWS Solutions Architect"],
        "soft_skills": ["leadership", "teamwork"],
        "education": "B.Tech",
        "cgpa": 8.5,
        "projects_count": 4,
        "notable_achievements": ["Built a scalable API"],
        "overall_score": 72,
        "candidate_summary": "Mid-level backend developer.",
        "resume_text": "Jane Smith\njane@example.com\nPython FastAPI Docker",
        "filename": "jane_resume.pdf",
    }
    if overrides:
        data.update(overrides)
    return data


# =====================================================================
# 1. AUTHENTICATION TESTS
# =====================================================================

class TestAuthentication:
    """Tests for auth.py authentication module."""

    def test_password_hash_and_verify(self):
        """Password hashing and verification should work correctly."""
        password = "SecurePassword123!"
        hashed = hash_password(password)

        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False

    def test_generated_admin_password_is_hashed_for_render(self, monkeypatch):
        """A Render-generated password is hashed before login verification."""
        import auth

        password = "render-generated-secret"
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", "")
        monkeypatch.setattr(auth, "ADMIN_PASSWORD", password)
        monkeypatch.setattr(auth, "ADMIN_PASSWORD_HASH", "")

        auth._init_admin_credentials()

        assert auth.ADMIN_PASSWORD_HASH != password
        assert verify_password(password, auth.ADMIN_PASSWORD_HASH)

    def test_create_and_decode_token(self):
        """JWT token creation and decoding should work."""
        payload = {"sub": "testuser", "role": "admin"}
        token = create_access_token(payload)

        assert token is not None
        assert isinstance(token, str)

        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == "testuser"
        assert decoded["role"] == "admin"

    def test_decode_invalid_token_returns_none(self):
        """Decoding an invalid token should return None."""
        assert decode_access_token("invalid.token.here") is None
        assert decode_access_token("") is None

    def test_authenticate_user_valid(self, monkeypatch):
        """authenticate_user should return user dict for valid credentials."""
        # Patch the admin password hash
        test_hash = hash_password("testpassword")
        monkeypatch.setattr("auth.ADMIN_PASSWORD_HASH", test_hash)
        monkeypatch.setattr("auth.ADMIN_USERNAME", "admin")

        result = authenticate_user("admin", "testpassword")
        assert result is not None
        assert result["sub"] == "admin"
        assert result["role"] == "admin"

    def test_authenticate_user_invalid_password(self, monkeypatch):
        """authenticate_user should return None for invalid password."""
        test_hash = hash_password("correctpassword")
        monkeypatch.setattr("auth.ADMIN_PASSWORD_HASH", test_hash)
        monkeypatch.setattr("auth.ADMIN_USERNAME", "admin")

        result = authenticate_user("admin", "wrongpassword")
        assert result is None

    def test_authenticate_user_invalid_username(self, monkeypatch):
        """authenticate_user should return None for invalid username."""
        test_hash = hash_password("testpassword")
        monkeypatch.setattr("auth.ADMIN_PASSWORD_HASH", test_hash)
        monkeypatch.setattr("auth.ADMIN_USERNAME", "admin")

        result = authenticate_user("wronguser", "testpassword")
        assert result is None

    def test_login_success(self, monkeypatch):
        """login should return token response for valid credentials."""
        test_hash = hash_password("testpassword")
        monkeypatch.setattr("auth.ADMIN_PASSWORD_HASH", test_hash)
        monkeypatch.setattr("auth.ADMIN_USERNAME", "admin")

        result = login("admin", "testpassword")
        assert result is not None
        assert "access_token" in result
        assert result["token_type"] == "bearer"
        assert "user" in result

    def test_login_failure(self, monkeypatch):
        """login should return None for invalid credentials."""
        test_hash = hash_password("correctpassword")
        monkeypatch.setattr("auth.ADMIN_PASSWORD_HASH", test_hash)

        result = login("admin", "wrongpassword")
        assert result is None


# =====================================================================
# 2. API AUTHORIZATION TESTS
# =====================================================================

class TestAPIAuthorization:
    """Tests for API endpoint authorization."""

    def test_health_endpoint_public(self, client):
        """Health endpoint should be accessible without auth."""
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ["healthy", "degraded"]

    def test_readiness_endpoint_public(self, client):
        """Readiness endpoint should be accessible without auth."""
        r = client.get("/api/readiness")
        # May return 503 if model not loaded, but shouldn't be 401
        assert r.status_code in [200, 503]

    def test_candidates_requires_auth(self, client):
        """Candidates list should require authentication."""
        r = client.get("/api/candidates")
        assert r.status_code == 401

    def test_candidate_detail_requires_auth(self, client):
        """Candidate detail should require authentication."""
        r = client.get("/api/candidates/1")
        assert r.status_code == 401

    def test_upload_requires_auth(self, client):
        """Upload endpoint should require authentication."""
        pdf = _make_minimal_pdf("Test content for authorization check")
        r = client.post("/api/upload", files=[
            ("files", ("test.pdf", pdf, "application/pdf")),
        ])
        assert r.status_code == 401

    def test_job_match_requires_auth(self, client):
        """Job match endpoint should require authentication."""
        r = client.post("/api/job-match", json={
            "job_title": "Test",
            "job_description": "Test job description for authorization",
        })
        assert r.status_code == 401

    def test_export_requires_auth(self, client):
        """Export endpoint should require authentication."""
        r = client.get("/api/export/json")
        assert r.status_code == 401

    def test_delete_requires_auth(self, client):
        """Delete endpoint should require authentication."""
        r = client.delete("/api/candidates/1")
        assert r.status_code == 401

    def test_delete_all_requires_auth(self, client):
        """Delete all endpoint should require authentication."""
        r = client.delete("/api/candidates")
        assert r.status_code == 401

    def test_stats_requires_auth(self, client):
        """Stats endpoint should require authentication."""
        r = client.get("/api/stats")
        assert r.status_code == 401

    def test_valid_auth_allows_access(self, client, auth_headers):
        """Valid auth token should allow access to protected endpoints."""
        # Stats
        r = client.get("/api/stats", headers=auth_headers)
        assert r.status_code == 200

        # Candidates
        r = client.get("/api/candidates", headers=auth_headers)
        assert r.status_code == 200

    def test_invalid_token_rejected(self, client):
        """Invalid token should be rejected."""
        headers = {"Authorization": "Bearer invalid_token"}
        r = client.get("/api/candidates", headers=headers)
        assert r.status_code == 401

    def test_expired_token_rejected(self, client):
        """Expired token should be rejected."""
        # Create an already-expired token
        from datetime import timedelta
        expired_token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(seconds=-1)
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        r = client.get("/api/candidates", headers=headers)
        assert r.status_code == 401


# =====================================================================
# 3. LOGIN API TESTS
# =====================================================================

class TestLoginAPI:
    """Tests for login API endpoint."""

    def test_login_endpoint_success(self, client, monkeypatch):
        """Login endpoint should return token for valid credentials."""
        test_hash = hash_password("testpassword")
        monkeypatch.setattr("auth.ADMIN_PASSWORD_HASH", test_hash)
        monkeypatch.setattr("auth.ADMIN_USERNAME", "admin")

        r = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "testpassword",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_endpoint_invalid_credentials(self, client, monkeypatch):
        """Login endpoint should return 401 for invalid credentials."""
        test_hash = hash_password("correctpassword")
        monkeypatch.setattr("auth.ADMIN_PASSWORD_HASH", test_hash)

        r = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrongpassword",
        })
        assert r.status_code == 401

    def test_login_endpoint_missing_fields(self, client):
        """Login endpoint should validate required fields."""
        r = client.post("/api/auth/login", json={})
        assert r.status_code == 422

    def test_auth_me_endpoint(self, client, auth_headers):
        """Auth me endpoint should return current user info."""
        r = client.get("/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "username" in data
        assert "role" in data


# =====================================================================
# 4. PDF VALIDATION TESTS
# =====================================================================

class TestPDFValidation:
    """Tests for PDF upload validation."""

    def test_valid_pdf_accepted(self):
        """Valid PDF should pass validation."""
        pdf = _make_minimal_pdf("John Doe\njohn@email.com\n" + "Python Developer " * 10)
        is_valid, error = pdf_validator.validate_file(
            type('obj', (object,), {'filename': 'test.pdf'})(),
            pdf
        )
        assert is_valid is True
        assert error is None

    def test_invalid_extension_rejected(self):
        """Non-PDF extension should be rejected."""
        pdf = _make_minimal_pdf("Test content")
        fake_file = type('obj', (object,), {'filename': 'test.txt'})()
        is_valid, error = pdf_validator.validate_file(fake_file, pdf)
        assert is_valid is False
        assert "extension" in error.lower()

    def test_empty_file_rejected(self):
        """Empty file should be rejected."""
        fake_file = type('obj', (object,), {'filename': 'test.pdf'})()
        is_valid, error = pdf_validator.validate_file(fake_file, b"")
        assert is_valid is False

    def test_too_small_file_rejected(self):
        """Very small file should be rejected."""
        fake_file = type('obj', (object,), {'filename': 'test.pdf'})()
        is_valid, error = pdf_validator.validate_file(fake_file, b"test")
        assert is_valid is False

    def test_corrupted_pdf_rejected(self):
        """Corrupted PDF should be rejected."""
        fake_file = type('obj', (object,), {'filename': 'test.pdf'})()
        is_valid, error = pdf_validator.validate_file(fake_file, b"%PDF-1.4\ncorrupted data")
        assert is_valid is False

    def test_non_pdf_content_rejected(self):
        """Non-PDF content should be rejected."""
        fake_file = type('obj', (object,), {'filename': 'test.pdf'})()
        is_valid, error = pdf_validator.validate_file(fake_file, b"Not a PDF at all, just plain text content")
        assert is_valid is False

    def test_batch_validation(self):
        """Batch validation should handle mixed files."""
        from fastapi import UploadFile
        import io

        good_pdf = _make_minimal_pdf("Good content " * 20)
        bad_content = b"Not a PDF"

        # Create mock upload files
        class MockUploadFile:
            def __init__(self, filename, content):
                self.filename = filename
                self.file = io.BytesIO(content)

        files = [
            MockUploadFile("good.pdf", good_pdf),
            MockUploadFile("bad.txt", bad_content),
        ]

        valid_files, errors = pdf_validator.validate_batch(files)

        assert len(valid_files) == 1
        assert len(errors) == 1


# =====================================================================
# 5. FILENAME SANITIZATION TESTS
# =====================================================================

class TestFilenameSanitization:
    """Tests for filename sanitization."""

    def test_normal_filename(self):
        """Normal filename should pass through."""
        result = sanitize_filename("resume.pdf")
        assert result == "resume.pdf"

    def test_path_traversal_removed(self):
        """Path traversal attempts should be removed."""
        result = sanitize_filename("../../../etc/passwd.pdf")
        assert ".." not in result
        assert "/" not in result
        assert result.endswith(".pdf")

    def test_special_characters_removed(self):
        """Special characters should be replaced."""
        result = sanitize_filename("resume<script>.pdf")
        assert "<" not in result
        assert ">" not in result

    def test_empty_filename_generates_one(self):
        """Empty filename should generate a safe name."""
        result = sanitize_filename("")
        assert result.endswith(".pdf")
        assert len(result) > 5

    def test_long_filename_truncated(self):
        """Very long filename should be truncated."""
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 204  # 200 + .pdf


# =====================================================================
# 6. RATE LIMITING TESTS
# =====================================================================

class TestRateLimiting:
    """Tests for rate limiting."""

    def test_rate_limiter_allows_requests(self):
        """Rate limiter should allow requests under limit."""
        limiter = InMemoryRateLimiter(requests_per_minute=10)

        class MockRequest:
            headers = {}
            client = type('obj', (object,), {'host': '127.0.0.1'})()

        request = MockRequest()

        for i in range(5):
            is_allowed, rate_info = limiter.is_allowed(request)
            assert is_allowed is True

    def test_rate_limiter_blocks_over_limit(self):
        """Rate limiter should block requests over limit."""
        limiter = InMemoryRateLimiter(requests_per_minute=5)

        class MockRequest:
            headers = {}
            client = type('obj', (object,), {'host': '127.0.0.1'})()

        request = MockRequest()

        # Use up the limit
        for i in range(5):
            limiter.is_allowed(request)

        # Next request should be blocked
        is_allowed, rate_info = limiter.is_allowed(request)
        assert is_allowed is False

    def test_rate_limiter_uses_x_forwarded_for(self):
        """Rate limiter should respect X-Forwarded-For header."""
        limiter = InMemoryRateLimiter(requests_per_minute=5)

        class MockRequest:
            headers = {"X-Forwarded-For": "192.168.1.1"}
            client = type('obj', (object,), {'host': '127.0.0.1'})()

        request = MockRequest()
        is_allowed, _ = limiter.is_allowed(request)
        assert is_allowed is True


# =====================================================================
# 7. DATABASE TESTS
# =====================================================================

class TestDatabase:
    """Tests for database operations."""

    def test_save_and_retrieve_candidate(self):
        """Save and retrieve candidate should work."""
        cid = save_candidate(_sample_candidate())
        assert cid > 0
        c = get_candidate(cid)
        assert c is not None
        assert c["candidate_name"] == "Jane Smith"

    def test_get_nonexistent_candidate(self):
        """Get nonexistent candidate should return None."""
        c = get_candidate(99999)
        assert c is None

    def test_delete_candidate(self):
        """Delete candidate should work."""
        cid = save_candidate(_sample_candidate())
        assert delete_candidate(cid) is True
        assert get_candidate(cid) is None

    def test_delete_nonexistent_candidate(self):
        """Delete nonexistent candidate should return False."""
        result = delete_candidate(99999)
        assert result is False

    def test_delete_all_candidates(self):
        """Delete all candidates should work."""
        save_candidate(_sample_candidate())
        save_candidate(_sample_candidate({"candidate_name": "Bob Jones"}))
        count = delete_all_candidates()
        assert count >= 2
        assert get_all_candidates() == []

    def test_count_candidates(self):
        """Count candidates should return correct count."""
        save_candidate(_sample_candidate())
        save_candidate(_sample_candidate({"candidate_name": "Another"}))
        count = count_candidates()
        assert count == 2

    def test_pagination(self):
        """Pagination should limit results."""
        for i in range(10):
            save_candidate(_sample_candidate({"candidate_name": f"Candidate {i}"}))

        page1 = get_all_candidates(limit=5, offset=0)
        page2 = get_all_candidates(limit=5, offset=5)

        assert len(page1) == 5
        assert len(page2) == 5
        # Ensure different candidates
        names1 = {c["candidate_name"] for c in page1}
        names2 = {c["candidate_name"] for c in page2}
        assert names1.isdisjoint(names2)

    def test_search_candidates(self):
        """Search should filter candidates."""
        save_candidate(_sample_candidate({"candidate_name": "Alice Wonderland"}))
        save_candidate(_sample_candidate({"candidate_name": "Bob Builder"}))
        results = get_all_candidates(search="Alice")
        assert len(results) == 1
        assert results[0]["candidate_name"] == "Alice Wonderland"

    def test_min_score_filter(self):
        """Min score filter should work."""
        save_candidate(_sample_candidate({"overall_score": 90}))
        save_candidate(_sample_candidate({"overall_score": 20}))
        results = get_all_candidates(min_score=50)
        assert all(c["overall_score"] >= 50 for c in results)


# =====================================================================
# 8. API ENDPOINT TESTS (AUTHENTICATED)
# =====================================================================

class TestAPIEndpoints:
    """Tests for API endpoints with authentication."""

    def test_upload_valid_pdf(self, client, auth_headers):
        """Upload valid PDF should succeed."""
        pdf = _make_minimal_pdf(
            "John Doe\njohn@email.com\n+1-555-123-4567\n"
            "Python Developer with 5 years experience\n"
            "Skills: Python, JavaScript, Docker, AWS, React"
        )
        r = client.post("/api/upload", files=[
            ("files", ("resume.pdf", pdf, "application/pdf")),
        ], headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] >= 1

    def test_upload_non_pdf(self, client, auth_headers):
        """Upload non-PDF should fail validation."""
        r = client.post("/api/upload", files=[
            ("files", ("resume.txt", b"not a pdf content", "text/plain")),
        ], headers=auth_headers)
        data = r.json()
        assert data.get("failed", 0) > 0 or len(data.get("errors", [])) > 0

    def test_list_candidates_paginated(self, client, auth_headers):
        """List candidates should return paginated results."""
        # Upload a candidate first (text must exceed the 50-char extraction floor)
        pdf = _make_minimal_pdf(
            "Test Candidate\ntest@email.com\n"
            "Python Developer with 4 years of experience building REST services\n"
            "Skills: Python, FastAPI, Docker, AWS"
        )
        upload_r = client.post("/api/upload", files=[
            ("files", ("test.pdf", pdf, "application/pdf")),
        ], headers=auth_headers)
        assert upload_r.json().get("success", 0) >= 1, upload_r.json()

        r = client.get("/api/candidates", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "candidates" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["total"] >= 1

    def test_get_candidate_by_id(self, client, auth_headers):
        """Get candidate by ID should work."""
        pdf = _make_minimal_pdf(
            "Carol Test\ncarol@test.com\n"
            "React Developer with 6 years of frontend engineering experience\n"
            "Skills: React, TypeScript, Node.js, GraphQL"
        )
        upload_r = client.post("/api/upload", files=[
            ("files", ("carol.pdf", pdf, "application/pdf")),
        ], headers=auth_headers)
        candidates = upload_r.json().get("candidates", [])
        assert candidates, upload_r.json()

        cid = candidates[0]["id"]
        r = client.get(f"/api/candidates/{cid}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == cid

    def test_delete_candidate(self, client, auth_headers):
        """Delete candidate should work."""
        pdf = _make_minimal_pdf(
            "Delete Me\ndel@test.com\n"
            "Backend Developer with 5 years of experience in distributed systems\n"
            "Skills: Go, Kubernetes, PostgreSQL, gRPC"
        )
        upload_r = client.post("/api/upload", files=[
            ("files", ("del.pdf", pdf, "application/pdf")),
        ], headers=auth_headers)
        candidates = upload_r.json().get("candidates", [])
        assert candidates, upload_r.json()

        cid = candidates[0]["id"]
        r = client.delete(f"/api/candidates/{cid}", headers=auth_headers)
        assert r.status_code == 200

    def test_job_match_with_candidates(self, client, auth_headers):
        """Job match should work with candidates."""
        # Upload a candidate first (text must exceed the 50-char extraction floor)
        pdf = _make_minimal_pdf(
            "Match Test\nmatch@test.com\n"
            "Python Django Developer with 5 years of backend experience\n"
            "Skills: Python, Django, REST APIs, Docker, PostgreSQL"
        )
        upload_r = client.post("/api/upload", files=[
            ("files", ("match.pdf", pdf, "application/pdf")),
        ], headers=auth_headers)
        assert upload_r.json().get("success", 0) >= 1, upload_r.json()

        r = client.post("/api/job-match", json={
            "job_title": "Python Developer",
            "job_description": "Need a Python developer experienced in Django REST APIs and Docker",
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "candidates" in data
        assert "total_candidates" in data

    def test_job_match_no_candidates(self, client, auth_headers):
        """Job match should fail with no candidates."""
        # Delete all candidates first
        client.delete("/api/candidates", headers=auth_headers)

        r = client.post("/api/job-match", json={
            "job_title": "Python Developer",
            "job_description": "Need Python developer with 3 years experience",
        }, headers=auth_headers)
        assert r.status_code == 400

    def test_export_json(self, client, auth_headers):
        """Export JSON should work."""
        r = client.get("/api/export/json", headers=auth_headers)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/json")

    def test_export_csv(self, client, auth_headers):
        """Export CSV should work."""
        r = client.get("/api/export/csv", headers=auth_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")


# =====================================================================
# 9. ERROR HANDLING TESTS
# =====================================================================

class TestErrorHandling:
    """Tests for error handling."""

    def test_404_candidate_not_found(self, client, auth_headers):
        """Non-existent candidate should return 404."""
        r = client.get("/api/candidates/99999", headers=auth_headers)
        assert r.status_code == 404

    def test_404_delete_nonexistent(self, client, auth_headers):
        """Delete non-existent candidate should return 404."""
        r = client.delete("/api/candidates/99999", headers=auth_headers)
        assert r.status_code == 404

    def test_422_invalid_job_match_request(self, client, auth_headers):
        """Invalid job match request should return 422."""
        r = client.post("/api/job-match", json={}, headers=auth_headers)
        assert r.status_code == 422

    def test_422_short_job_description(self, client, auth_headers):
        """Short job description should fail validation."""
        r = client.post("/api/job-match", json={
            "job_title": "Dev",
            "job_description": "short",
        }, headers=auth_headers)
        assert r.status_code == 422


# =====================================================================
# 10. FRONTEND SERVING TESTS
# =====================================================================

class TestFrontendServing:
    """Tests for frontend serving."""

    def test_frontend_served(self, client):
        """Frontend should be served at root."""
        r = client.get("/")
        assert r.status_code == 200


# =====================================================================
# Run with: pytest test_comprehensive.py -v
# =====================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
