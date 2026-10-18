"""
Pydantic Models — Request/Response validation for FastAPI
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict


# ==================== AUTHENTICATION MODELS ====================

class LoginRequest(BaseModel):
    """Login request body."""
    username: str = Field(..., min_length=1, max_length=100, description="Username")
    password: str = Field(..., min_length=1, max_length=200, description="Password")


class TokenResponse(BaseModel):
    """Token response after successful login."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")
    user: Dict[str, str] = Field(default_factory=dict)


class UserInfo(BaseModel):
    """Authenticated user information."""
    username: str
    role: str
    name: Optional[str] = None


# ==================== RESPONSE MODELS ====================

class CandidateResponse(BaseModel):
    """Single candidate data returned from API."""
    id: Optional[int] = None
    candidate_name: str = "Name not detected"
    email: str = "Not provided"
    phone: str = "Not provided"
    linkedin: str = ""
    experience_years: int = 0
    internship_experience_years: int = 0
    experience_level: str = "Not specified"
    specialization: str = "Software Developer"
    technologies: List[str] = []
    certifications: List[str] = []
    soft_skills: List[str] = []
    education: str = "Not specified"
    cgpa: Optional[float] = None
    projects_count: int = 0
    notable_achievements: List[str] = []
    overall_score: int = 0
    candidate_summary: str = ""
    filename: str = ""
    created_at: Optional[str] = None

    # Job match fields (only present after matching)
    job_match_score: Optional[float] = None
    match_level: Optional[str] = None
    skill_gaps: Optional[List[str]] = None
    suggestions: Optional[List[Dict[str, str]]] = None


class CandidateListResponse(BaseModel):
    """Paginated candidate list response."""
    total: int
    count: int
    offset: int
    limit: int
    candidates: List[CandidateResponse]


class StatsResponse(BaseModel):
    """Dashboard statistics."""
    total_candidates: int = 0
    avg_score: float = 0.0
    top_score: int = 0
    experience_distribution: Dict[str, int] = {}
    top_technologies: Dict[str, int] = {}
    specialization_distribution: Dict[str, int] = {}


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: str
    database: Optional[Dict] = None


class DeletionResponse(BaseModel):
    """Response for deletion operations."""
    message: str
    count: Optional[int] = None
    id: Optional[int] = None


# ==================== REQUEST MODELS ====================

class JobMatchRequest(BaseModel):
    """Request body for job matching."""
    job_title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Job title",
    )
    job_description: str = Field(
        ...,
        min_length=10,
        max_length=20000,
        description="Full job description",
    )

    @field_validator("job_title", "job_description")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ExportRequest(BaseModel):
    """Export format selection."""
    format: str = Field(default="json", description="Export format: json or csv")

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("json", "csv"):
            raise ValueError("format must be 'json' or 'csv'")
        return v


class PaginationParams(BaseModel):
    """Reusable pagination parameters."""
    limit: int = Field(default=50, ge=1, le=200, description="Max rows to return")
    offset: int = Field(default=0, ge=0, description="Rows to skip")
