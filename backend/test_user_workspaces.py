"""Regression tests for public signup and isolated candidate workspaces."""

import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

import database
from rate_limiter import registration_limiter


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "workspace_test.sqlite")
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db()
    registration_limiter.reset()
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def _create_account(client, username):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Very-Secure-Test-Password-42"},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    return {
        "Authorization": f"Bearer {result['access_token']}",
    }, result


def _minimal_pdf():
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Synthetic Candidate\ncandidate@example.test\n"
        "Backend developer experienced with Python, FastAPI, PostgreSQL and Docker.\n"
        "Education: Bachelor of Technology. Projects include a secure API platform.",
        fontsize=12,
    )
    content = doc.tobytes()
    doc.close()
    return content


def test_registration_normalizes_username_and_rejects_duplicates(client):
    headers, account = _create_account(client, "  Research.Team  ")

    assert account["user"] == {"username": "research.team", "role": "user"}
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "user"

    login_response = client.post(
        "/api/auth/login",
        json={"username": "RESEARCH.TEAM", "password": "Very-Secure-Test-Password-42"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "research.team"

    duplicate = client.post(
        "/api/auth/register",
        json={"username": "research.team", "password": "Very-Secure-Test-Password-42"},
    )
    assert duplicate.status_code == 409

    reserved = client.post(
        "/api/auth/register",
        json={"username": "admin", "password": "Very-Secure-Test-Password-42"},
    )
    assert reserved.status_code == 409

    invalid = client.post(
        "/api/auth/register",
        json={"username": "ab", "password": "short"},
    )
    assert invalid.status_code == 422


def test_candidate_data_and_mutations_are_scoped_to_each_account(client):
    headers_a, _ = _create_account(client, "workspace-a")
    upload = client.post(
        "/api/upload",
        headers=headers_a,
        files=[("files", ("synthetic.pdf", _minimal_pdf(), "application/pdf"))],
    )
    assert upload.status_code == 200, upload.text
    candidates = upload.json()["candidates"]
    assert len(candidates) == 1
    candidate_id = candidates[0]["id"]

    database.save_job_description(
        "Private role",
        "Only visible to the owner of the corresponding workspace.",
        owner_username="workspace-a",
    )

    headers_b, _ = _create_account(client, "workspace-b")
    assert client.get("/api/candidates", headers=headers_b).json()["total"] == 0
    assert client.get("/api/stats", headers=headers_b).json()["total_candidates"] == 0
    assert client.get(
        f"/api/candidates/{candidate_id}", headers=headers_b
    ).status_code == 404
    assert client.delete(
        f"/api/candidates/{candidate_id}", headers=headers_b
    ).status_code == 404
    assert client.get("/api/job-descriptions", headers=headers_b).json()["total"] == 0

    exported = client.get("/api/export/json", headers=headers_b).json()
    assert exported["total_candidates"] == 0
    assert exported["candidates"] == []

    assert client.post("/api/candidates/reprocess", headers=headers_b).json()["updated"] == 0
    assert client.delete("/api/candidates", headers=headers_b).json()["count"] == 0

    owned = client.get("/api/candidates", headers=headers_a).json()
    assert owned["total"] == 1
    assert owned["candidates"][0]["id"] == candidate_id
    assert client.get("/api/job-descriptions", headers=headers_a).json()["total"] == 1


def test_legacy_records_are_assigned_to_configured_admin(tmp_path, monkeypatch):
    db_path = str(tmp_path / "legacy.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT NOT NULL,
            overall_score INTEGER DEFAULT 0,
            experience_level TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        """CREATE TABLE job_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    conn.execute("INSERT INTO candidates (candidate_name) VALUES ('Legacy record')")
    conn.execute(
        "INSERT INTO job_descriptions (title, description) VALUES ('Legacy role', 'Role')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db()

    with sqlite3.connect(db_path) as conn:
        candidate_owner = conn.execute(
            "SELECT owner_username FROM candidates WHERE candidate_name = 'Legacy record'"
        ).fetchone()[0]
        job_owner = conn.execute(
            "SELECT owner_username FROM job_descriptions WHERE title = 'Legacy role'"
        ).fetchone()[0]

    assert candidate_owner == database.settings.admin_username
    assert job_owner == database.settings.admin_username
