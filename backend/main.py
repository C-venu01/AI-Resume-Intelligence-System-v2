"""
AI Resume Intelligence System 2.0 — FastAPI Backend
Main application with all API routes.
Serves both API and frontend static files.

Security Features:
- JWT authentication on sensitive endpoints
- Rate limiting on uploads and expensive operations
- Secure CORS configuration
- Input validation on all uploads
- Security headers
- Privacy-aware error handling
"""

import os
import csv
import json
import io
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, UploadFile, File, Query, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse

# Local modules
from config import settings
from logging_config import get_logger, set_request_id, sanitize_error_message
from auth import (
    require_auth,
    login,
    add_security_headers,
)
from rate_limiter import rate_limit, upload_limiter, match_limiter
from validators import pdf_validator, sanitize_filename
from pdf_extractor import extract_text_from_pdf
from resume_analyzer import analyze_resume
from embedding_engine import rank_candidates_for_job, is_model_ready
from database import (
    init_db, save_candidate, get_all_candidates, get_candidate,
    delete_candidate, delete_all_candidates, get_stats,
    save_job_description, get_job_descriptions,
    save_match_result, health_check as db_health_check,
    count_candidates,
)
from models import (
    JobMatchRequest, StatsResponse,
    CandidateListResponse, HealthResponse, DeletionResponse,
    LoginRequest, TokenResponse,
)

logger = get_logger(__name__)


# ==================== APP SETUP ====================

app = FastAPI(
    title="AI Resume Intelligence System 2.0",
    description="Cloud-Based Hiring Copilot — Analyze, Match & Rank Candidates",
    version="2.0.0",
    docs_url="/docs" if settings.environment == "development" else None,  # Disable docs in production
    redoc_url="/redoc" if settings.environment == "development" else None,
)

# ==================== SECURITY MIDDLEWARE ====================

# Add security headers to all responses
app.middleware("http")(add_security_headers)


# Request ID middleware for tracing
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add unique request ID to each request for tracing."""
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        import uuid
        request_id = str(uuid.uuid4())[:8]
    set_request_id(request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ==================== CORS ====================

# Use explicit allowlist from configuration (never ["*"] with credentials)
cors_origins = settings.cors_origins_list

if settings.environment == "production" and not cors_origins:
    logger.warning("No CORS origins configured for production. API may be inaccessible from frontend.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


# ==================== STARTUP/SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    # Validate production settings
    issues = settings.validate_production_settings()
    if issues:
        for issue in issues:
            logger.error(f"Configuration issue: {issue}")

    # Initialize database
    init_db()

    logger.info("Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Application shutting down")


# ==================== PUBLIC ENDPOINTS ====================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    Public - no authentication required.
    Checks application and database status.
    """
    db_status = db_health_check()

    return {
        "status": "healthy" if db_status["status"] == "healthy" else "degraded",
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
    }


@app.get("/api/readiness")
async def readiness_check():
    """
    Readiness probe for container orchestration.
    Checks if the application is ready to receive traffic.
    """
    checks = {
        "database": db_health_check()["status"] == "healthy",
        "embedding_model": is_model_ready(),
    }

    all_healthy = all(checks.values())

    if not all_healthy:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks}
        )

    return {"status": "ready", "checks": checks}


# ==================== AUTHENTICATION ENDPOINTS ====================

@app.post("/api/auth/login", response_model=TokenResponse)
async def auth_login(request: LoginRequest):
    """
    Authenticate and receive a JWT token.
    Rate-limited to prevent brute force attacks.
    Public endpoint.
    """
    result = login(request.username, request.password)

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info(f"User logged in: {request.username}")
    return result


@app.get("/api/auth/me")
async def get_current_user(user: dict = Depends(require_auth)):
    """Get current authenticated user info."""
    return {
        "username": user.get("sub"),
        "role": user.get("role"),
    }


# ==================== UPLOAD & ANALYZE (PROTECTED) ====================

@app.post("/api/upload")
async def upload_resumes(
    files: List[UploadFile] = File(...),
    user: dict = Depends(require_auth),
    _: dict = Depends(rate_limit(upload_limiter)),
):
    """
    Upload and analyze resume PDFs.

    Requires authentication.
    Rate-limited.
    Validates files for security.

    Accepts multiple PDF files, extracts text, analyzes, and stores results.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Validate all files first
    valid_files, validation_errors = pdf_validator.validate_batch(files)

    results = []
    errors = validation_errors.copy()

    for file, content in valid_files:
        safe_filename = sanitize_filename(file.filename)

        try:
            # Extract text
            text = extract_text_from_pdf(content)
            if not text:
                errors.append({
                    "filename": file.filename,
                    "error": "Could not extract text from PDF"
                })
                continue

            # Analyze resume
            analysis = analyze_resume(text, safe_filename)
            analysis["resume_text"] = text  # Store for re-analysis

            # Save to database
            candidate_id = save_candidate(analysis)
            analysis["id"] = candidate_id

            # Remove resume_text from response (privacy, size)
            analysis.pop("resume_text", None)
            results.append(analysis)

        except Exception as e:
            logger.error(f"Error processing {file.filename}: {type(e).__name__}")
            errors.append({
                "filename": file.filename,
                "error": sanitize_error_message(e, include_details=settings.debug)
            })

    return {
        "success": len(results),
        "failed": len(errors),
        "candidates": results,
        "errors": errors,
    }


# ==================== CANDIDATES CRUD (PROTECTED) ====================

@app.get("/api/candidates", response_model=CandidateListResponse)
async def list_candidates(
    search: str = Query("", description="Search by name, specialization, or tech"),
    sort_by: str = Query("overall_score", description="Sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
    min_score: int = Query(0, ge=0, le=100),
    experience_level: str = Query("", description="Filter by level"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user: dict = Depends(require_auth),
):
    """
    Get all candidates with optional filtering, sorting, and pagination.

    Requires authentication.
    Returns paginated results.
    """
    candidates = get_all_candidates(
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        min_score=min_score,
        experience_level=experience_level,
        limit=limit,
        offset=offset,
        include_resume_text=False,
    )

    total = count_candidates(
        search=search,
        min_score=min_score,
        experience_level=experience_level,
    )

    return {
        "total": total,
        "count": len(candidates),
        "offset": offset,
        "limit": limit,
        "candidates": candidates,
    }


@app.get("/api/candidates/{candidate_id}")
async def get_single_candidate(
    candidate_id: int,
    user: dict = Depends(require_auth),
):
    """
    Get a single candidate by ID.

    Requires authentication.
    """
    candidate = get_candidate(candidate_id, include_resume_text=False)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@app.delete("/api/candidates/{candidate_id}", response_model=DeletionResponse)
async def remove_candidate(
    candidate_id: int,
    user: dict = Depends(require_auth),
):
    """
    Delete a candidate by ID.

    Requires authentication.
    """
    if delete_candidate(candidate_id):
        logger.info(f"Candidate {candidate_id} deleted by {user.get('sub')}")
        return {"message": "Candidate deleted", "id": candidate_id}
    raise HTTPException(status_code=404, detail="Candidate not found")


@app.delete("/api/candidates", response_model=DeletionResponse)
async def remove_all_candidates(user: dict = Depends(require_auth)):
    """
    Delete all candidates.

    Requires authentication.
    This is a destructive operation.
    """
    count = delete_all_candidates()
    logger.warning(f"All candidates ({count}) deleted by {user.get('sub')}")
    return {"message": f"Deleted {count} candidate(s)", "count": count}


# ==================== JOB MATCHING (PROTECTED) ====================

@app.post("/api/job-match")
async def job_match(
    request: JobMatchRequest,
    user: dict = Depends(require_auth),
    _: dict = Depends(rate_limit(match_limiter)),
):
    """
    Match all candidates against a job description using semantic similarity.

    Requires authentication.
    Rate-limited (computationally expensive).
    Returns candidates ranked by match score with skill gaps.

    Note: Match scores are similarity estimates, not probabilities of hiring success.
    """
    # Get all candidates from database (without resume_text for matching)
    candidates = get_all_candidates(include_resume_text=False)
    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No candidates in database. Upload resumes first."
        )

    # Save job description
    jd_id = save_job_description(request.job_title, request.job_description)

    # Rank candidates against JD
    try:
        ranked = rank_candidates_for_job(candidates, request.job_description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Job matching failed: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail="Job matching failed. Please try again."
        )

    # Save match results
    for candidate in ranked:
        if candidate.get("id"):
            save_match_result(candidate["id"], jd_id, {
                "match_score": candidate.get("job_match_score", 0),
                "match_level": candidate.get("match_level", ""),
                "skill_gaps": candidate.get("skill_gaps", []),
                "suggestions": candidate.get("suggestions", []),
            })

    logger.info(f"Job match completed: {request.job_title}, {len(ranked)} candidates")

    return {
        "job_title": request.job_title,
        "total_candidates": len(ranked),
        "candidates": ranked,
    }


# ==================== STATISTICS (PROTECTED) ====================

@app.get("/api/stats", response_model=StatsResponse)
async def dashboard_stats(user: dict = Depends(require_auth)):
    """
    Get dashboard statistics.

    Requires authentication.
    """
    return get_stats()


# ==================== EXPORT (PROTECTED) ====================

@app.get("/api/export/{format}")
async def export_candidates(
    format: str = "json",
    user: dict = Depends(require_auth),
):
    """
    Export all candidates as JSON or CSV.

    Requires authentication.
    Exports personal data (names, emails, phones).
    """
    candidates = get_all_candidates(include_resume_text=False)

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
        logger.info(f"CSV export by {user.get('sub')}: {len(candidates)} candidates")
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
            "export_date": datetime.now(timezone.utc).isoformat(),
            "exported_by": user.get("sub"),
            "total_candidates": len(candidates),
            "candidates": candidates,
        }
        json_str = json.dumps(export_data, indent=2, default=str)
        logger.info(f"JSON export by {user.get('sub')}: {len(candidates)} candidates")
        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            },
        )


# ==================== JOB DESCRIPTIONS (PROTECTED) ====================

@app.get("/api/job-descriptions")
async def list_job_descriptions(user: dict = Depends(require_auth)):
    """
    Get all saved job descriptions.

    Requires authentication.
    """
    jds = get_job_descriptions()
    return {"total": len(jds), "job_descriptions": jds}


# ==================== SERVE FRONTEND ====================

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the main frontend page."""
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Frontend not found. API is running at /api"}
else:
    @app.get("/")
    async def root():
        return {"message": "AI Resume Intelligence System 2.0 API", "docs": "/docs"}


# ==================== ERROR HANDLERS ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler with privacy-aware error messages."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers or {},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Generic exception handler - never expose internal errors to clients."""
    logger.error(f"Unhandled exception: {type(exc).__name__}")

    # In production, return generic error
    if settings.environment == "production":
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred. Please try again later."},
        )

    # In development, include more details
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {str(exc)[:200]}"},
    )


# ==================== STARTUP ====================

if __name__ == "__main__":
    import uvicorn
    print("\n>>> Starting AI Resume Intelligence System 2.0")
    print(f">>> Environment: {settings.environment}")
    print(f">>> API Docs: http://localhost:{settings.port}/docs")
    print(f">>> Dashboard: http://localhost:{settings.port}/")
    print("=" * 50)
    uvicorn.run(app, host=settings.host, port=settings.port)
