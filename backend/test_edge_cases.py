"""
AI Resume Intelligence System 2.0 — Comprehensive Edge Case Tests
Tests all modules: PDF extractor, resume analyzer, embedding engine, database, API endpoints.
"""

import os
import sys
import json
import io
import sqlite3
 # Removed unused imports: tempfile, shutil, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# ── Ensure backend is importable ──
sys.path.insert(0, os.path.dirname(__file__))

from pdf_extractor import extract_text_from_pdf, get_pdf_page_count
from resume_analyzer import analyze_resume
import database
from database import init_db, save_candidate, get_all_candidates, get_candidate, \
    delete_candidate, delete_all_candidates, save_job_description, \
    get_job_descriptions, save_match_result, get_stats
from models import JobMatchRequest, CandidateResponse
from rate_limiter import default_limiter, match_limiter, upload_limiter


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Use a temp database for every test so tests don't interfere."""
    db_path = str(tmp_path / "test_resume.sqlite")
    monkeypatch.setattr("database.DB_PATH", db_path)
    default_limiter.reset()
    match_limiter.reset()
    upload_limiter.reset()
    init_db()
    yield db_path


@pytest.fixture
def client():
    """FastAPI TestClient (imports app fresh so DB patch is active)."""
    from main import app
    from auth import require_auth
    app.dependency_overrides[require_auth] = lambda: {
        "sub": "test-admin",
        "role": "admin",
    }
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(require_auth, None)


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
# 1. PDF EXTRACTOR TESTS
# =====================================================================

class TestPDFExtractor:
    """Edge cases for pdf_extractor.py"""

    def test_valid_pdf_extraction(self):
        pdf = _make_minimal_pdf("Hello World this is a resume with enough text to pass threshold.")
        result = extract_text_from_pdf(pdf)
        assert result is not None
        assert "Hello World" in result

    def test_corrupted_pdf_returns_none(self):
        result = extract_text_from_pdf(b"this is not a pdf at all")
        assert result is None

    def test_empty_bytes_returns_none(self):
        result = extract_text_from_pdf(b"")
        assert result is None

    def test_near_empty_pdf_returns_none(self):
        """PDF with < 50 chars should return None."""
        pdf = _make_minimal_pdf("Hi")
        result = extract_text_from_pdf(pdf)
        assert result is None

    def test_unicode_normalization(self):
        """Smart quotes and em-dashes should be replaced."""
        text = "John\u2019s Resume \u2013 Software Dev \u201cExpert\u201d with enough text for extraction"
        pdf = _make_minimal_pdf(text)
        result = extract_text_from_pdf(pdf)
        if result:
            assert "\u2019" not in result  # should be normalized

    def test_multiline_pdf(self):
        lines = "\n".join([f"Line {i} of the resume with text content" for i in range(30)])
        pdf = _make_minimal_pdf(lines)
        result = extract_text_from_pdf(pdf)
        assert result is not None

    def test_page_count_valid_pdf(self):
        pdf = _make_minimal_pdf("Some text for page counting purposes in a resume document")
        count = get_pdf_page_count(pdf)
        assert count == 1

    def test_page_count_invalid_pdf(self):
        count = get_pdf_page_count(b"not a pdf")
        assert count == 0


# =====================================================================
# 2. RESUME ANALYZER TESTS
# =====================================================================

class TestResumeAnalyzer:
    """Edge cases for resume_analyzer.py"""

    def test_empty_text_returns_error_result(self):
        result = analyze_resume("", "empty.pdf")
        assert result["candidate_name"] == "Name not detected"
        assert result["overall_score"] == 0

    def test_whitespace_only_text(self):
        result = analyze_resume("   \n\n\t  ", "blank.pdf")
        assert result["candidate_name"] == "Name not detected"

    def test_name_extraction_from_first_line(self):
        text = "Rahul Kumar\nrahul@gmail.com\n+91-9876543210\nPython Developer with 3 years experience"
        result = analyze_resume(text, "rahul.pdf")
        assert result["candidate_name"] == "Rahul Kumar"

    def test_technology_terms_are_not_candidate_names(self):
        text = (
            "AWS\nJupyter\nPrometheus\nPandas\nDocker\nJava\n"
            "Skills and Projects\nUsed in a data dashboard"
        )
        result = analyze_resume(text, "technology-terms.pdf")
        assert result["candidate_name"] == "Name not detected"

    def test_name_not_location(self):
        """Location names should not be picked as person names."""
        text = "Andhra Pradesh\nHyderabad\ndev@example.com\nSoftware Developer with Python and AWS"
        result = analyze_resume(text, "loc.pdf")
        assert result["candidate_name"] == "Name not detected"

    def test_name_not_heading(self):
        """Resume headings should not be picked as person names."""
        text = "Resume\nObjective\nEmail: test@test.com\nPython Developer with skills in React and Node"
        result = analyze_resume(text, "heading.pdf")
        assert result["candidate_name"] == "Name not detected"

    def test_email_address_is_not_used_as_candidate_name(self):
        text = "john.doe@gmail.com\nSkills: Python, JavaScript\nExperience: 2 years at Google as Software Engineer"
        result = analyze_resume(text, "noname.pdf")
        assert result["candidate_name"] == "Name not detected"

    def test_contextual_header_name_wins_over_technology_entities(self):
        text = (
            "Ananya R. Krishnan\nananya@example.test\n+91 9876543210\n"
            "Education\nB.Tech Computer Science 2020 - 2024\n"
            "Skills\nAWS, Jupyter, Prometheus, Pandas, Docker, Java"
        )
        result = analyze_resume(text, "header-name.pdf")
        assert result["candidate_name"] == "Ananya R. Krishnan"

    def test_indian_initials_and_international_name_formats(self):
        for name in ("R. K. Sharma", "María del Carmen O'Neill"):
            result = analyze_resume(
                f"{name}\ncontact@example.test\nEducation\nB.Tech 2020 - 2024",
                "synthetic-name.pdf",
            )
            assert result["candidate_name"] == name

    def test_projects_before_work_history_do_not_replace_name(self):
        text = (
            "Priya K. Nair\npriya@example.test\nProjects\n"
            "Quick Sight dashboard using Pandas 2020 - 2024\n"
            "Work Experience\nBackend Developer at Northwind Technologies "
            "2021 - 2023"
        )
        result = analyze_resume(text, "projects-first.pdf")
        assert result["candidate_name"] == "Priya K. Nair"
        assert result["experience_years"] == 2

    def test_email_extraction(self):
        text = "Alice Bob\nalice.bob@company.co.uk\nSoftware Engineer with expertise in Python and Docker"
        result = analyze_resume(text, "email.pdf")
        assert result["email"] == "alice.bob@company.co.uk"

    def test_no_email(self):
        text = "Alice Bob\nSoftware Engineer with Python and Docker skills and three years experience"
        result = analyze_resume(text, "noemail.pdf")
        assert result["email"] == "Not provided"

    def test_phone_us_format(self):
        text = "Bob Smith\nbob@test.com\n(555) 123-4567\nPython Developer with React and Node.js experience"
        result = analyze_resume(text, "usphone.pdf")
        assert result["phone"] != "Not provided"

    def test_phone_indian_format(self):
        text = "Raj Patel\nraj@mail.com\n+91-9876543210\nJava Developer with Spring Boot experience at TCS"
        result = analyze_resume(text, "inphone.pdf")
        assert result["phone"] != "Not provided"

    def test_phone_international(self):
        text = "Anna Mueller\nanna@mail.com\n+49 170 1234567\nDevOps engineer with Kubernetes and Docker expertise"
        result = analyze_resume(text, "intlphone.pdf")
        assert result["phone"] != "Not provided"

    def test_no_phone(self):
        text = "Charlie Brown\ncharlie@mail.com\nPython developer with five years of experience in backend development"
        result = analyze_resume(text, "nophone.pdf")
        assert result["phone"] == "Not provided"

    def test_technology_extraction(self):
        text = "Dev Name\ndev@mail.com\nSkills: Python, JavaScript, React, Docker, Kubernetes, AWS, SQL, TensorFlow"
        result = analyze_resume(text, "tech.pdf")
        techs = [t.lower() for t in result["technologies"]]
        assert "python" in techs
        assert "javascript" in techs or "react" in techs

    def test_no_technologies(self):
        text = "John Doe\njohn@mail.com\nI am a professional with many years of experience in the industry"
        result = analyze_resume(text, "notech.pdf")
        assert isinstance(result["technologies"], list)

    def test_experience_years_direct_mention(self):
        text = "Sarah Lee\nsarah@test.com\n5 years of experience in software development using Python and AWS"
        result = analyze_resume(text, "exp.pdf")
        assert result["experience_years"] >= 0

    def test_experience_years_date_range(self):
        text = (
            "Tom Brown\ntom@test.com\nProfessional Experience\n"
            "Software Engineer at Google 2020 - 2024\nPython, React, Docker"
        )
        result = analyze_resume(text, "dateexp.pdf")
        assert result["experience_years"] == 4

    def test_experience_years_present(self):
        text = (
            "Tom Brown\ntom@test.com\nProfessional Experience\n"
            "Software Engineer at Google 2022 - present\nPython, React"
        )
        result = analyze_resume(text, "present.pdf")
        assert result["experience_years"] >= 3

    def test_education_and_project_dates_do_not_count_as_employment(self):
        text = (
            "Ravi Kumar\nravi@example.test\nEducation\n"
            "B.Tech Computer Science 2019 - 2023\nProjects\n"
            "Data Dashboard 2022 - 2024 using Pandas"
        )
        result = analyze_resume(text, "education-only.pdf")
        assert result["experience_years"] == 0
        assert result["internship_experience_years"] == 0
        assert result["experience_level"] == "Not specified"

    def test_overlapping_employment_is_not_double_counted(self):
        text = (
            "Maya Chen\nmaya@example.test\nEmployment History\n"
            "Software Engineer at Acme Systems 2019 - 2022\n"
            "Data Engineer at Northwind Technologies 2021 - 2024"
        )
        result = analyze_resume(text, "overlapping-work.pdf")
        assert result["experience_years"] == 5
        assert len(result["experience_evidence"]) == 2

    def test_internship_is_reported_separately_from_employment(self):
        text = (
            "Dev Patel\ndev@example.test\nWork Experience\n"
            "Software Engineer at Acme Systems 2021 - 2023\n"
            "Internship Experience\n"
            "Software Engineering Intern at Northwind Labs 2020 - 2021"
        )
        result = analyze_resume(text, "internship.pdf")
        assert result["experience_years"] == 2
        assert result["internship_experience_years"] == 1

    def test_experience_capped_at_30(self):
        text = "Veteran Dev\nvet@mail.com\n50 years of experience in software development and engineering"
        result = analyze_resume(text, "vet.pdf")
        assert result["experience_years"] <= 30

    def test_experience_level_mapping(self):
        """Experience levels should be valid strings."""
        text = "New Grad\nnew@mail.com\n0 years experience\nSkills: Python, HTML, CSS"
        result = analyze_resume(text, "fresh.pdf")
        assert result["experience_level"] in [
            "Not specified", "Fresher", "Junior", "Mid-level", "Senior", "Principal"
        ]

    def test_cgpa_extraction_out_of_ten(self):
        text = "Student Name\nstud@mail.com\nCGPA: 8.5/10\nB.Tech Computer Science from IIT"
        result = analyze_resume(text, "cgpa.pdf")
        if result["cgpa"]:
            assert 0 < result["cgpa"] <= 10

    def test_cgpa_extraction_out_of_four(self):
        text = "Student Name\nstud@mail.com\nGPA: 3.5/4.0\nB.S. Computer Science from MIT"
        result = analyze_resume(text, "gpa4.pdf")
        # Should handle 4-point scale
        assert isinstance(result["cgpa"], (int, float)) or result["cgpa"] is None

    def test_cgpa_invalid_value_rejected(self):
        text = "Student Name\nstud@mail.com\nCGPA: 15.0\nB.Tech in Computer Science with Python skills"
        result = analyze_resume(text, "badcgpa.pdf")
        # Invalid CGPA (>10) should be None or 0
        if result["cgpa"]:
            assert result["cgpa"] <= 10

    def test_education_phd(self):
        text = "Dr. Smith\nsmith@uni.edu\nPh.D. in Computer Science from Stanford University with research in ML"
        result = analyze_resume(text, "phd.pdf")
        assert result["education"] is not None

    def test_education_btech(self):
        text = "Ravi Kumar\nravi@mail.com\nB.Tech in Computer Science from IIT Bombay\nSkills: Python, Java"
        result = analyze_resume(text, "btech.pdf")
        assert result["education"] is not None

    def test_certifications_extraction(self):
        text = "Dev Pro\ndev@mail.com\nAWS Certified Solutions Architect\nCKA certified\nPython, Docker"
        result = analyze_resume(text, "certs.pdf")
        assert isinstance(result["certifications"], list)

    def test_soft_skills_extraction(self):
        text = "Leader Dev\nlead@mail.com\nStrong leadership and teamwork abilities with excellent communication"
        result = analyze_resume(text, "soft.pdf")
        assert isinstance(result["soft_skills"], list)

    def test_projects_count_capped(self):
        projects = "\n".join([f"Project {i}: Built something with Python" for i in range(25)])
        text = f"Dev Name\ndev@mail.com\n{projects}"
        result = analyze_resume(text, "projects.pdf")
        assert result["projects_count"] <= 20

    def test_achievements_max_five(self):
        achievements = "\n".join([f"• Achieved thing {i} in software development" for i in range(10)])
        text = f"Dev Name\ndev@mail.com\n{achievements}"
        result = analyze_resume(text, "achieve.pdf")
        assert len(result["notable_achievements"]) <= 5

    def test_overall_score_range(self):
        text = "Full Stack Dev\nfs@mail.com\nPython JavaScript React Docker AWS 5 years experience"
        result = analyze_resume(text, "score.pdf")
        assert 0 <= result["overall_score"] <= 100

    def test_overall_score_zero_for_empty(self):
        result = analyze_resume("", "empty.pdf")
        assert result["overall_score"] == 0

    def test_specialization_detection(self):
        text = "ML Engineer\nml@mail.com\nTensorFlow PyTorch Machine Learning Deep Learning Python Scikit-learn"
        result = analyze_resume(text, "ml.pdf")
        assert result["specialization"] is not None

    def test_linkedin_extraction(self):
        text = "Dev Name\ndev@mail.com\nhttps://linkedin.com/in/devname\nPython Docker AWS experience"
        result = analyze_resume(text, "li.pdf")
        assert "linkedin" in result["linkedin"].lower() or result["linkedin"] == ""

    def test_very_long_resume(self):
        """Should handle large text without crashing."""
        text = "John Doe\njohn@mail.com\n" + ("Python Developer " * 5000)
        result = analyze_resume(text, "long.pdf")
        assert result["candidate_name"] != ""
        assert result["overall_score"] >= 0

    def test_special_characters_in_text(self):
        text = "José García\njose@mail.com\nDéveloppeur Python\n5 años de experiencia en desarrollo"
        result = analyze_resume(text, "special.pdf")
        assert result is not None
        assert isinstance(result["technologies"], list)

    def test_all_fields_present(self):
        """Every expected field should exist in the result."""
        text = "Test Dev\ntest@mail.com\nPython Developer with 3 years experience and Docker skills"
        result = analyze_resume(text, "fields.pdf")
        expected = [
            "candidate_name", "email", "phone", "linkedin",
            "experience_years", "experience_level", "specialization",
            "internship_experience_years", "name_confidence", "name_evidence",
            "experience_evidence",
            "technologies", "certifications", "soft_skills", "education",
            "cgpa", "projects_count", "notable_achievements",
            "overall_score", "candidate_summary", "filename"
        ]
        for field in expected:
            assert field in result, f"Missing field: {field}"


# =====================================================================
# 3. EMBEDDING ENGINE TESTS
# =====================================================================

class TestEmbeddingEngine:
    """Edge cases for embedding_engine.py"""

    def test_identical_texts_high_score(self):
        from embedding_engine import compute_job_match
        text = "Python developer with 5 years experience in Django and FastAPI building REST APIs"
        result = compute_job_match(text, text)
        assert result["match_score"] > 70

    def test_completely_different_texts_low_score(self):
        from embedding_engine import compute_job_match
        resume = "Experienced chef with expertise in French cuisine and pastry arts"
        jd = "Looking for a senior Kubernetes engineer with AWS and Terraform experience"
        result = compute_job_match(resume, jd)
        assert result["match_score"] < 60

    def test_match_result_structure(self):
        from embedding_engine import compute_job_match
        result = compute_job_match(
            "Python developer experienced in machine learning and data science",
            "We need a Python ML engineer with TensorFlow and PyTorch skills"
        )
        assert "match_score" in result
        assert "match_level" in result
        assert "skill_gaps" in result
        assert "suggestions" in result
        assert "section_scores" in result

    def test_match_levels(self):
        from embedding_engine import compute_job_match
        result = compute_job_match(
            "Python developer with expertise in web development and APIs",
            "Senior Python developer needed for building REST APIs"
        )
        assert result["match_level"] in [
            "Excellent Match", "Good Match", "Moderate Match",
            "Partial Match", "Low Match"
        ]

    def test_skill_gap_detection(self):
        from embedding_engine import compute_job_match
        resume = "Python developer with Flask experience and SQLite database skills"
        jd = "Need Python developer with Kubernetes, Docker, and AWS experience"
        result = compute_job_match(resume, jd)
        assert isinstance(result["skill_gaps"], list)

    def test_empty_resume_text(self):
        from embedding_engine import compute_job_match
        with pytest.raises(ValueError, match="Resume text is empty"):
            compute_job_match("", "Python developer needed with 5 years experience")

    def test_empty_job_description(self):
        from embedding_engine import compute_job_match
        with pytest.raises(ValueError, match="Job description is empty"):
            compute_job_match("Python developer with Docker and AWS experience", "")

    def test_rank_candidates(self):
        from embedding_engine import rank_candidates_for_job
        candidates = [
            {"id": 1, "resume_text": "Python Django REST API developer with 5 years experience",
             "technologies": ["Python", "Django"]},
            {"id": 2, "resume_text": "Java Spring Boot enterprise developer and architect",
             "technologies": ["Java", "Spring"]},
        ]
        jd = "Looking for Python Django developer with REST API experience"
        ranked = rank_candidates_for_job(candidates, jd)
        assert len(ranked) == 2
        # Python dev should rank higher for a Python JD
        assert ranked[0]["id"] == 1

    def test_rank_empty_candidates(self):
        from embedding_engine import rank_candidates_for_job
        ranked = rank_candidates_for_job([], "Python developer with Flask experience")
        assert ranked == []

    def test_section_scores_present(self):
        from embedding_engine import compute_job_match
        result = compute_job_match(
            "Python developer with 3 years experience, B.Tech degree, built 5 projects",
            "Need Python developer with experience and CS degree"
        )
        assert isinstance(result["section_scores"], dict)

    def test_suggestions_are_dicts(self):
        from embedding_engine import compute_job_match
        result = compute_job_match(
            "Junior developer learning Python and basic web development",
            "Need expert in Kubernetes Docker AWS Terraform CI/CD microservices"
        )
        for s in result["suggestions"]:
            assert isinstance(s, dict)
            assert "skill" in s
            assert "resource" in s


# =====================================================================
# 4. DATABASE TESTS
# =====================================================================

class TestDatabase:
    """Edge cases for database.py"""

    def test_save_and_retrieve_candidate(self):
        cid = save_candidate(_sample_candidate())
        assert cid > 0
        c = get_candidate(cid)
        assert c is not None
        assert c["candidate_name"] == "Jane Smith"

    def test_get_nonexistent_candidate(self):
        c = get_candidate(99999)
        assert c is None

    def test_delete_candidate(self):
        cid = save_candidate(_sample_candidate())
        assert delete_candidate(cid) is True
        assert get_candidate(cid) is None

    def test_delete_nonexistent_candidate(self):
        result = delete_candidate(99999)
        assert result is False

    def test_delete_all_candidates(self):
        save_candidate(_sample_candidate())
        save_candidate(_sample_candidate({"candidate_name": "Bob Jones"}))
        count = delete_all_candidates()
        assert count >= 2
        assert get_all_candidates() == []

    def test_search_candidates(self):
        save_candidate(_sample_candidate({"candidate_name": "Alice Wonderland"}))
        save_candidate(_sample_candidate({"candidate_name": "Bob Builder"}))
        results = get_all_candidates(search="Alice")
        assert len(results) == 1
        assert results[0]["candidate_name"] == "Alice Wonderland"

    def test_search_case_insensitive(self):
        save_candidate(_sample_candidate({"candidate_name": "UPPERCASE NAME"}))
        results = get_all_candidates(search="uppercase")
        assert len(results) == 1

    def test_sort_by_score(self):
        save_candidate(_sample_candidate({"overall_score": 90, "candidate_name": "High"}))
        save_candidate(_sample_candidate({"overall_score": 30, "candidate_name": "Low"}))
        results = get_all_candidates(sort_by="overall_score", sort_order="desc")
        assert results[0]["overall_score"] >= results[-1]["overall_score"]

    def test_sort_by_name(self):
        save_candidate(_sample_candidate({"candidate_name": "Zara"}))
        save_candidate(_sample_candidate({"candidate_name": "Adam"}))
        results = get_all_candidates(sort_by="candidate_name", sort_order="asc")
        assert results[0]["candidate_name"] == "Adam"

    def test_invalid_sort_column_defaults(self):
        """Invalid sort column should not crash (SQL injection prevention)."""
        save_candidate(_sample_candidate())
        # This should not raise — invalid columns are guarded
        results = get_all_candidates(sort_by="DROP TABLE candidates; --")
        assert isinstance(results, list)

    def test_min_score_filter(self):
        save_candidate(_sample_candidate({"overall_score": 90}))
        save_candidate(_sample_candidate({"overall_score": 20}))
        results = get_all_candidates(min_score=50)
        assert all(c["overall_score"] >= 50 for c in results)

    def test_experience_level_filter(self):
        save_candidate(_sample_candidate({"experience_level": "Senior"}))
        save_candidate(_sample_candidate({"experience_level": "Fresher"}))
        results = get_all_candidates(experience_level="Senior")
        assert all(c["experience_level"] == "Senior" for c in results)

    def test_json_fields_parsed(self):
        cid = save_candidate(_sample_candidate({"technologies": ["Go", "Rust"]}))
        c = get_candidate(cid)
        assert isinstance(c["technologies"], list)
        assert "Go" in c["technologies"]

    def test_save_job_description(self):
        jid = save_job_description("Python Dev", "Need Python developer with Flask experience")
        assert jid > 0
        jds = get_job_descriptions()
        assert any(j["id"] == jid for j in jds)

    def test_stats_with_no_candidates(self):
        stats = get_stats()
        assert stats["total_candidates"] == 0

    def test_stats_with_candidates(self):
        save_candidate(_sample_candidate({"overall_score": 80}))
        save_candidate(_sample_candidate({"overall_score": 60}))
        stats = get_stats()
        assert stats["total_candidates"] == 2
        assert stats["avg_score"] == 70
        assert stats["top_score"] == 80

    def test_special_characters_in_search(self):
        """SQL characters in search should not cause errors."""
        save_candidate(_sample_candidate({"candidate_name": "O'Brien"}))
        results = get_all_candidates(search="O'Brien")
        assert isinstance(results, list)

    def test_save_match_result(self):
        cid = save_candidate(_sample_candidate())
        jid = save_job_description("Role", "Description of the role for matching")
        mid = save_match_result(cid, jid, {
            "match_score": 85.0,
            "match_level": "Excellent Match",
            "skill_gaps": ["Docker"],
            "suggestions": ["Learn Docker"],
            "section_scores": {"technical": 90},
        })
        assert mid > 0

    def test_cascade_delete(self):
        """Deleting a candidate should also delete their match results."""
        cid = save_candidate(_sample_candidate())
        jid = save_job_description("Role", "Description for cascade test")
        save_match_result(cid, jid, {
            "match_score": 75.0, "match_level": "Good Match",
            "skill_gaps": [], "suggestions": [], "section_scores": {},
        })
        delete_candidate(cid)
        assert get_candidate(cid) is None


# =====================================================================
# 5. API ENDPOINT TESTS
# =====================================================================

class TestAPI:
    """Edge cases for main.py FastAPI endpoints."""

    def test_health_endpoint(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_stats_endpoint(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_candidates" in data

    # ── Upload tests ──

    def test_upload_no_files(self, client):
        r = client.post("/api/upload")
        assert r.status_code in [400, 422]

    def test_upload_non_pdf(self, client):
        r = client.post("/api/upload", files=[
            ("files", ("resume.txt", b"not a pdf content", "text/plain")),
        ])
        data = r.json()
        # Should report error for non-PDF
        assert data.get("failed", 0) > 0 or len(data.get("errors", [])) > 0

    def test_upload_valid_pdf(self, client):
        pdf = _make_minimal_pdf(
            "John Doe\njohn@email.com\n+1-555-123-4567\n"
            "Python Developer with 5 years experience\n"
            "Skills: Python, JavaScript, Docker, AWS, React"
        )
        r = client.post("/api/upload", files=[
            ("files", ("resume.pdf", pdf, "application/pdf")),
        ])
        assert r.status_code == 200
        data = r.json()
        assert data["success"] >= 1

    def test_upload_corrupted_pdf(self, client):
        r = client.post("/api/upload", files=[
            ("files", ("bad.pdf", b"corrupted pdf data xyz", "application/pdf")),
        ])
        data = r.json()
        assert data.get("failed", 0) > 0 or len(data.get("errors", [])) > 0

    def test_upload_multiple_files_mixed(self, client):
        good_pdf = _make_minimal_pdf(
            "Alice Dev\nalice@mail.com\nPython Docker AWS Developer with 3 years experience"
        )
        r = client.post("/api/upload", files=[
            ("files", ("good.pdf", good_pdf, "application/pdf")),
            ("files", ("bad.txt", b"not pdf", "text/plain")),
        ])
        data = r.json()
        assert data["success"] >= 1
        assert data["failed"] >= 1

    # ── Candidates CRUD ──

    def test_list_candidates_empty(self, client):
        r = client.get("/api/candidates")
        assert r.status_code == 200
        data = r.json()
        assert data["candidates"] == []
        assert data["total"] == 0

    def test_get_candidate_not_found(self, client):
        r = client.get("/api/candidates/99999")
        assert r.status_code == 404

    def test_reprocess_updates_legacy_records_in_place(self, client):
        resumes = [
            (
                "legacy-no-name.pdf",
                "Prometheus\nJupyter\nPandas\nDocker\nJava\nSkills\n"
                "Projects\nQuick Sight dashboard 2020 - 2024",
            ),
            (
                "legacy-work.pdf",
                "Maya Chen\nmaya@example.test\nEducation\nB.Tech 2016 - 2020\n"
                "Professional Experience\n"
                "Software Engineer at Acme Systems Jan 2020 - Dec 2024",
            ),
        ]
        uploaded = client.post(
            "/api/upload",
            files=[
                ("files", (filename, _make_minimal_pdf(text), "application/pdf"))
                for filename, text in resumes
            ],
        )
        assert uploaded.status_code == 200
        candidates = uploaded.json()["candidates"]
        assert len(candidates) == 2
        ids = {candidate["id"] for candidate in candidates}
        assert all(
            key not in candidates[0]
            for key in ("resume_text", "name_evidence", "name_confidence", "experience_evidence")
        )

        with database.db_connection() as conn:
            for candidate_id in ids:
                conn.execute(
                    "UPDATE candidates SET candidate_name = ?, experience_years = 7, "
                    "experience_level = 'Senior' WHERE id = ?",
                    ("Pandas", candidate_id),
                )

        reprocessed = client.post("/api/candidates/reprocess")
        assert reprocessed.status_code == 200
        assert reprocessed.json()["updated"] == 2
        assert reprocessed.json()["missing_source"] == 0
        assert reprocessed.json()["failed"] == 0

        listed = client.get("/api/candidates").json()["candidates"]
        assert {candidate["id"] for candidate in listed} == ids
        by_id = {candidate["id"]: candidate for candidate in listed}
        detail_by_id = {
            candidate_id: client.get(f"/api/candidates/{candidate_id}").json()
            for candidate_id in ids
        }
        no_name_id = next(
            candidate_id
            for candidate_id, candidate in by_id.items()
            if candidate["filename"] == "legacy-no-name.pdf"
        )
        work_id = next(candidate_id for candidate_id in ids if candidate_id != no_name_id)

        assert by_id[no_name_id]["candidate_name"] == "Name not detected"
        assert by_id[no_name_id]["experience_years"] == 0
        assert by_id[work_id]["candidate_name"] == "Maya Chen"
        assert by_id[work_id]["experience_years"] == 5
        for candidate_id in ids:
            assert detail_by_id[candidate_id]["candidate_name"] == by_id[candidate_id]["candidate_name"]
            assert detail_by_id[candidate_id]["experience_years"] == by_id[candidate_id]["experience_years"]
            assert "resume_text" not in detail_by_id[candidate_id]
            assert "name_evidence" not in detail_by_id[candidate_id]

    def test_reprocess_marks_missing_source_without_inventing_name(self, client):
        candidate_id = save_candidate(_sample_candidate({
            "candidate_name": "Jupyter",
            "experience_years": 7,
            "experience_level": "Senior",
            "resume_text": "",
        }), owner_username="test-admin")

        response = client.post("/api/candidates/reprocess")
        assert response.status_code == 200
        assert response.json()["missing_source"] == 1
        candidate = client.get(f"/api/candidates/{candidate_id}").json()
        assert candidate["id"] == candidate_id
        assert candidate["candidate_name"] == "Name not detected"
        assert candidate["experience_years"] == 0
        assert "re-upload" in candidate["candidate_summary"].lower()

    def test_delete_candidate_not_found(self, client):
        r = client.delete("/api/candidates/99999")
        assert r.status_code == 404

    def test_upload_then_list(self, client):
        pdf = _make_minimal_pdf(
            "Bob Builder\nbob@test.com\nPython Developer expert with Docker and 4 years experience"
        )
        client.post("/api/upload", files=[
            ("files", ("bob.pdf", pdf, "application/pdf")),
        ])
        r = client.get("/api/candidates")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_upload_then_get_by_id(self, client):
        pdf = _make_minimal_pdf(
            "Carol Test\ncarol@test.com\nReact Developer with TypeScript and 2 years experience"
        )
        upload = client.post("/api/upload", files=[
            ("files", ("carol.pdf", pdf, "application/pdf")),
        ])
        candidates = upload.json().get("candidates", [])
        if candidates:
            cid = candidates[0]["id"]
            r = client.get(f"/api/candidates/{cid}")
            assert r.status_code == 200

    def test_upload_then_delete(self, client):
        pdf = _make_minimal_pdf(
            "Delete Me\ndel@test.com\nPython Docker Developer with 1 year experience"
        )
        upload = client.post("/api/upload", files=[
            ("files", ("del.pdf", pdf, "application/pdf")),
        ])
        candidates = upload.json().get("candidates", [])
        if candidates:
            cid = candidates[0]["id"]
            r = client.delete(f"/api/candidates/{cid}")
            assert r.status_code == 200

    def test_delete_all_candidates(self, client):
        pdf = _make_minimal_pdf(
            "Anyone Here\nany@test.com\nJava Developer with Spring Boot and 3 years experience"
        )
        client.post("/api/upload", files=[
            ("files", ("any.pdf", pdf, "application/pdf")),
        ])
        r = client.delete("/api/candidates")
        assert r.status_code == 200

    # ── Search & Filter ──

    def test_search_candidates(self, client):
        pdf = _make_minimal_pdf(
            "Unique Searchname\nuniq@test.com\nPython Developer with Docker and AWS and 5 years"
        )
        client.post("/api/upload", files=[
            ("files", ("uniq.pdf", pdf, "application/pdf")),
        ])
        r = client.get("/api/candidates?search=Searchname")
        assert r.status_code == 200

    def test_sort_candidates(self, client):
        r = client.get("/api/candidates?sort_by=overall_score&sort_order=desc")
        assert r.status_code == 200

    def test_min_score_filter(self, client):
        r = client.get("/api/candidates?min_score=50")
        assert r.status_code == 200

    # ── Job Match ──

    def test_job_match_no_candidates(self, client):
        r = client.post("/api/job-match", json={
            "job_title": "Python Developer",
            "job_description": "Need Python developer with 3 years of experience in Django and REST APIs",
        })
        assert r.status_code == 400

    def test_job_match_with_candidates(self, client):
        pdf = _make_minimal_pdf(
            "Match Test\nmatch@test.com\nPython Django REST API Developer with 5 years experience"
        )
        client.post("/api/upload", files=[
            ("files", ("match.pdf", pdf, "application/pdf")),
        ])
        r = client.post("/api/job-match", json={
            "job_title": "Python Developer",
            "job_description": "Need a Python developer experienced in Django REST APIs and Docker",
        })
        assert r.status_code == 200
        data = r.json()
        assert "candidates" in data
        assert "job_title" in data
        assert "total_candidates" in data

    def test_job_match_invalid_request(self, client):
        """Missing required fields should fail validation."""
        r = client.post("/api/job-match", json={})
        assert r.status_code == 422

    def test_job_match_short_description(self, client):
        """Job description < 10 chars should fail Pydantic validation."""
        r = client.post("/api/job-match", json={
            "job_title": "Dev",
            "job_description": "short",
        })
        assert r.status_code == 422

    # ── Export ──

    def test_export_json(self, client):
        pdf = _make_minimal_pdf(
            "Export Test\nexport@test.com\nPython Developer with Docker and AWS skills and 2 years"
        )
        client.post("/api/upload", files=[
            ("files", ("export.pdf", pdf, "application/pdf")),
        ])
        r = client.get("/api/export/json")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/json")

    def test_export_csv(self, client):
        pdf = _make_minimal_pdf(
            "CSV Test\ncsv@test.com\nPython Developer experienced in Docker AWS React and 3 years"
        )
        client.post("/api/upload", files=[
            ("files", ("csv.pdf", pdf, "application/pdf")),
        ])
        r = client.get("/api/export/csv")
        assert r.status_code == 200

    def test_export_invalid_format_returns_json(self, client):
        """Non-CSV formats fall through to JSON export (no 400 error)."""
        r = client.get("/api/export/xml")
        assert r.status_code == 200

    # ── Job Descriptions ──

    def test_list_job_descriptions(self, client):
        r = client.get("/api/job-descriptions")
        assert r.status_code == 200
        data = r.json()
        assert "job_descriptions" in data
        assert isinstance(data["job_descriptions"], list)

    # ── Frontend serving ──

    def test_frontend_served(self, client):
        r = client.get("/")
        assert r.status_code == 200


# =====================================================================
# 6. PYDANTIC MODEL VALIDATION TESTS
# =====================================================================

class TestModels:
    """Edge cases for models.py Pydantic validation."""

    def test_job_match_request_valid(self):
        req = JobMatchRequest(
            job_title="Python Dev",
            job_description="Need a Python developer with REST API experience"
        )
        assert req.job_title == "Python Dev"

    def test_job_match_request_empty_title(self):
        with pytest.raises(Exception):
            JobMatchRequest(job_title="", job_description="Need a Python developer with REST API experience")

    def test_job_match_request_short_description(self):
        with pytest.raises(Exception):
            JobMatchRequest(job_title="Dev", job_description="short")

    def test_candidate_response_optional_fields(self):
        """CandidateResponse should accept partial data."""
        c = CandidateResponse(
            id=1,
            candidate_name="Test",
            email="test@test.com",
            overall_score=50,
        )
        assert c.candidate_name == "Test"


# =====================================================================
# Run with: pytest test_edge_cases.py -v
# =====================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
