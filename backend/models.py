"""
Pydantic Models — Request/Response validation for FastAPI
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict


# ==================== RESPONSE MODELS ====================

class CandidateResponse(BaseModel):
    """Single candidate data returned from API."""
    id: Optional[int] = None
    candidate_name: str = "Unknown"
    email: str = "Not provided"
    phone: str = "Not provided"
    linkedin: str = ""
    experience_years: int = 0
    experience_level: str = "Fresher"
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


class StatsResponse(BaseModel):
    """Dashboard statistics."""
    total_candidates: int = 0
    avg_score: float = 0.0
    top_score: int = 0
    experience_distribution: Dict[str, int] = {}
    top_technologies: Dict[str, int] = {}
    specialization_distribution: Dict[str, int] = {}


# ==================== REQUEST MODELS ====================

class JobMatchRequest(BaseModel):
    """Request body for job matching."""
    job_title: str = Field(..., min_length=1, description="Job title")
    job_description: str = Field(..., min_length=10, description="Full job description")


class ExportRequest(BaseModel):
    """Export format selection."""
    format: str = Field(default="json", description="Export format: json or csv")
