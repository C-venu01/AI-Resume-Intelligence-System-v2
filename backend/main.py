"""
AI Resume Intelligence System 2.0 — FastAPI Backend
Main application with all API routes.
Serves both API and frontend static files.
"""

import os
import csv
import json
import io
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

# Local modules
from pdf_extractor import extract_text_from_pdf
from resume_analyzer import analyze_resume
from embedding_engine import compute_job_match, rank_candidates_for_job
from database import (
    init_db, save_candidate, get_all_candidates, get_candidate,
    delete_candidate, delete_all_candidates, get_stats,
    save_job_description, get_job_descriptions,
    save_match_result,
)
from models import JobMatchRequest, CandidateResponse, StatsResponse

# ==================== APP SETUP ====================

app = FastAPI(
    title="AI Resume Intelligence System 2.0",
    description="Cloud-Based Hiring Copilot — Analyze, Match & Rank Candidates",
    version="2.0.0",
)

# CORS — allow frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
init_db()

# Prometheus metrics (optional — only if installed)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
    print("[App] Prometheus metrics enabled at /metrics")
except ImportError:
    print("[App] Prometheus not installed — metrics disabled")


# ==================== API ROUTES ====================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0", "timestamp": datetime.now().isoformat()}


# ---------- UPLOAD & ANALYZE ----------

@app.post("/api/upload")
async def upload_resumes(files: List[UploadFile] = File(...)):
    """
    Upload and analyze resume PDFs.
    Accepts multiple PDF files, extracts text, analyzes, and stores results.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    errors = []

    for file in files:
        # Validate file type
        if not file.filename.lower().endswith(".pdf"):
            errors.append({"filename": file.filename, "error": "Not a PDF file"})
            continue

        try:
            # Read file bytes
            pdf_bytes = await file.read()

            # Extract text
            text = extract_text_from_pdf(pdf_bytes)
            if not text:
                errors.append({"filename": file.filename, "error": "Could not extract text"})
                continue

            # Analyze resume
            analysis = analyze_resume(text, file.filename)
            analysis["resume_text"] = text  # Store for re-analysis

            # Save to database
            candidate_id = save_candidate(analysis)
            analysis["id"] = candidate_id

            # Remove resume_text from response (too large)
            analysis.pop("resume_text", None)
            results.append(analysis)

        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    return {
        "success": len(results),
        "failed": len(errors),
        "candidates": results,
        "errors": errors,
    }


# ---------- CANDIDATES CRUD ----------

@app.get("/api/candidates")
async def list_candidates(
    search: str = Query("", description="Search by name, specialization, or tech"),
    sort_by: str = Query("overall_score", description="Sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
    min_score: int = Query(0, ge=0, le=100),
    experience_level: str = Query("", description="Filter by level"),
):
    """Get all candidates with optional filtering and sorting."""
    candidates = get_all_candidates(
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        min_score=min_score,
        experience_level=experience_level,
    )
    return {"total": len(candidates), "candidates": candidates}


@app.get("/api/candidates/{candidate_id}")
async def get_single_candidate(candidate_id: int):
    """Get a single candidate by ID."""
    candidate = get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@app.delete("/api/candidates/{candidate_id}")
async def remove_candidate(candidate_id: int):
    """Delete a candidate by ID."""
    if delete_candidate(candidate_id):
        return {"message": "Candidate deleted", "id": candidate_id}
    raise HTTPException(status_code=404, detail="Candidate not found")


@app.delete("/api/candidates")
async def remove_all_candidates():
    """Delete all candidates."""
    count = delete_all_candidates()
    return {"message": f"Deleted {count} candidate(s)", "count": count}


# ---------- JOB MATCHING ----------

@app.post("/api/job-match")
async def job_match(request: JobMatchRequest):
    """
    Match all candidates against a job description using semantic similarity.
    Returns candidates ranked by match score with skill gaps.
    """
    # Get all candidates from database
    candidates = get_all_candidates()
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates in database. Upload resumes first.")

    # Save job description
    jd_id = save_job_description(request.job_title, request.job_description)

    # Rank candidates against JD
    ranked = rank_candidates_for_job(candidates, request.job_description)

    # Save match results
    for candidate in ranked:
        if candidate.get("id"):
            save_match_result(candidate["id"], jd_id, {
                "match_score": candidate.get("job_match_score", 0),
                "match_level": candidate.get("match_level", ""),
                "skill_gaps": candidate.get("skill_gaps", []),
                "suggestions": candidate.get("suggestions", []),
            })

    return {
        "job_title": request.job_title,
        "total_candidates": len(ranked),
        "candidates": ranked,
    }


# ---------- STATISTICS ----------

@app.get("/api/stats")
async def dashboard_stats():
    """Get dashboard statistics."""
    return get_stats()


# ---------- EXPORT ----------

@app.get("/api/export/{format}")
async def export_candidates(format: str = "json"):
    """Export all candidates as JSON or CSV."""
    candidates = get_all_candidates()

    if format.lower() == "csv":
        # Generate CSV
        output = io.StringIO()
        if candidates:
            writer = csv.DictWriter(output, fieldnames=candidates[0].keys())
            writer.writeheader()
            for c in candidates:
                # Flatten lists to comma-separated strings for CSV
                row = {}
                for key, val in c.items():
                    if isinstance(val, list):
                        row[key] = ", ".join(str(v) for v in val)
                    else:
                        row[key] = val
                writer.writerow(row)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            },
        )
    else:
        # JSON export
        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_candidates": len(candidates),
            "candidates": candidates,
        }
        json_str = json.dumps(export_data, indent=2, default=str)
        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            },
        )


# ---------- JOB DESCRIPTIONS ----------

@app.get("/api/job-descriptions")
async def list_job_descriptions():
    """Get all saved job descriptions."""
    jds = get_job_descriptions()
    return {"total": len(jds), "job_descriptions": jds}


# ==================== SERVE FRONTEND ====================

# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the main frontend page."""
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Frontend not found. API is running at /docs"}
else:
    @app.get("/")
    async def root():
        return {"message": "AI Resume Intelligence System 2.0 API", "docs": "/docs"}


# ==================== STARTUP ====================

if __name__ == "__main__":
    import uvicorn
    print("\n>>> Starting AI Resume Intelligence System 2.0")
    print(">>> API Docs: http://localhost:8000/docs")
    print(">>> Dashboard: http://localhost:8000/")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
