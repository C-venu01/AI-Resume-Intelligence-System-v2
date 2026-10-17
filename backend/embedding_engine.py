"""
Embedding Engine — Semantic Resume-Job Matching
Uses sentence-transformers to create embeddings and compute similarity.
Also performs skill gap analysis and suggests learning resources.
"""

import threading
import numpy as np
from typing import Dict, List, Tuple, Optional
from sentence_transformers import SentenceTransformer

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)

# ==================== MODEL LOADING ====================
# all-MiniLM-L6-v2: fast, lightweight (~80MB), 384-dim vectors
# Downloads automatically on first use, then cached locally
#
# Model is loaded once and cached for the process lifetime to avoid
# repeated (expensive) reloads during requests. A lock guards the
# lazy initialization against concurrent first-requests.

_model: Optional[SentenceTransformer] = None
_model_lock = threading.Lock()
_model_load_error: Optional[str] = None


class ModelUnavailableError(RuntimeError):
    """Raised when the embedding model could not be loaded or used."""


def _get_model() -> SentenceTransformer:
    """
    Lazy-load and cache the sentence-transformer model (thread-safe).

    The model is loaded at most once per process. If loading fails, the
    error is remembered so we fail fast on subsequent calls rather than
    retrying an expensive download on every request.
    """
    global _model, _model_load_error

    if _model is not None:
        return _model

    with _model_lock:
        # Double-checked locking: another thread may have loaded it
        if _model is not None:
            return _model

        if _model_load_error is not None:
            raise ModelUnavailableError(_model_load_error)

        try:
            logger.info("Loading sentence-transformers model (first use)...")
            _model = SentenceTransformer(settings.embedding_model)
            logger.info("Embedding model loaded successfully.")
        except Exception as e:
            _model_load_error = (
                "Embedding model is unavailable. It may not be installed or "
                "downloaded yet."
            )
            logger.error(f"Failed to load embedding model: {type(e).__name__}")
            raise ModelUnavailableError(_model_load_error) from e

    return _model


def is_model_ready() -> bool:
    """Check whether the embedding model is loaded (readiness probe)."""
    return _model is not None


# ==================== CORE MATCHING ====================

def compute_job_match(resume_text: str, job_description: str) -> Dict:
    """
    Compute semantic similarity between resume and job description.

    The returned ``match_score`` is a *semantic similarity estimate* (0–100),
    NOT a probability of hiring success or a measure of candidate quality.

    Args:
        resume_text: Full resume text.
        job_description: Job description text.

    Returns:
        Dictionary with match_score, skill_gaps, section_scores, and suggestions.

    Raises:
        ValueError: If either input is empty after stripping.
        ModelUnavailableError: If the embedding model cannot be loaded.
    """
    resume_text = (resume_text or "").strip()
    job_description = (job_description or "").strip()

    if not resume_text:
        raise ValueError("Resume text is empty")
    if not job_description:
        raise ValueError("Job description is empty")

    model = _get_model()

    # Encode both texts into vectors (single batched call = one model pass)
    embeddings = model.encode([resume_text, job_description])
    resume_vec = embeddings[0]
    jd_vec = embeddings[1]

    # Cosine similarity, clamped to the valid [-1, 1] range before scaling.
    # Real embeddings are typically non-negative, but we guard anyway so a
    # degenerate vector can never produce a score outside 0–100.
    similarity = max(-1.0, min(1.0, _cosine_similarity(resume_vec, jd_vec)))
    match_score = round(max(0.0, similarity) * 100, 1)  # 0-100%

    # Skill gap analysis
    skill_gaps = _find_skill_gaps(resume_text, job_description)

    # Generate suggestions
    suggestions = _generate_suggestions(skill_gaps)

    # Section-level matching for detailed breakdown
    section_scores = _compute_section_scores(model, resume_text, job_description)

    return {
        "match_score": match_score,
        "skill_gaps": skill_gaps,
        "suggestions": suggestions,
        "section_scores": section_scores,
        "match_level": _get_match_level(match_score),
    }


def rank_candidates_for_job(
    candidates: List[Dict],
    job_description: str,
    model: Optional[SentenceTransformer] = None,
) -> List[Dict]:
    """
    Rank multiple candidates against a job description.

    Encodes the job description once, then encodes all candidate texts in a
    single batched call — avoiding one model invocation per candidate.

    Args:
        candidates: List of candidate dictionaries (with resume_text or technologies).
        job_description: Job description text.
        model: Optional pre-loaded model (mainly for testing/injection).

    Returns:
        Candidates list sorted by match score (highest first).

    Raises:
        ValueError: If the job description is empty.
        ModelUnavailableError: If the embedding model cannot be loaded.
    """
    job_description = (job_description or "").strip()
    if not job_description:
        raise ValueError("Job description is empty")

    if not candidates:
        return []

    model = model or _get_model()

    # Encode JD once; encode all candidate texts in one batch.
    jd_embedding = model.encode([job_description])[0]
    candidate_texts = [_build_candidate_text(c) for c in candidates]
    candidate_embeddings = model.encode(candidate_texts)

    results = []
    for candidate, candidate_text, cand_embedding in zip(
        candidates, candidate_texts, candidate_embeddings
    ):
        similarity = max(-1.0, min(1.0, _cosine_similarity(cand_embedding, jd_embedding)))
        match_score = round(max(0.0, similarity) * 100, 1)

        candidate_result = dict(candidate)
        candidate_result["job_match_score"] = match_score
        candidate_result["match_level"] = _get_match_level(match_score)

        # Skill gap for this candidate
        skill_gaps = _find_skill_gaps(candidate_text, job_description)
        candidate_result["skill_gaps"] = skill_gaps
        candidate_result["suggestions"] = _generate_suggestions(skill_gaps)

        results.append(candidate_result)

    # Sort by match score descending; stable sort preserves original order on ties
    results.sort(key=lambda x: x["job_match_score"], reverse=True)
    return results


# ==================== SKILL GAP ANALYSIS ====================

def _find_skill_gaps(resume_text: str, job_description: str) -> List[str]:
    """
    Identify skills mentioned in job description but missing from resume.
    """
    # Common technology/skill keywords
    from resume_analyzer import TECH_DATABASE

    jd_lower = job_description.lower()
    resume_lower = resume_text.lower()

    gaps = []
    for tech, keywords in TECH_DATABASE.items():
        # Check if tech is in JD but not in resume
        in_jd = any(kw in jd_lower for kw in keywords)
        in_resume = any(kw in resume_lower for kw in keywords)
        if in_jd and not in_resume:
            gaps.append(tech)

    return gaps


# ==================== LEARNING SUGGESTIONS ====================

LEARNING_RESOURCES = {
    "Python": "Automate the Boring Stuff with Python (free online book)",
    "JavaScript": "JavaScript.info — Modern JavaScript Tutorial",
    "TypeScript": "TypeScript Handbook (typescriptlang.org)",
    "React": "React Official Tutorial (react.dev)",
    "Node.js": "NodeSchool.io — Free interactive workshops",
    "Java": "Java MOOC by University of Helsinki (free)",
    "Docker": "Docker Getting Started Tutorial (docs.docker.com)",
    "Kubernetes": "Kubernetes Basics on kubernetes.io",
    "AWS": "AWS Cloud Practitioner Essentials (free on Skill Builder)",
    "Azure": "Microsoft Learn — Azure Fundamentals (free)",
    "GCP": "Google Cloud Skills Boost (free tier available)",
    "Machine Learning": "Andrew Ng's ML Course on Coursera",
    "Deep Learning": "Fast.ai — Practical Deep Learning (free)",
    "TensorFlow": "TensorFlow Dev Certificate prep on Coursera",
    "PyTorch": "PyTorch Official Tutorials (pytorch.org)",
    "SQL": "SQLBolt — Learn SQL with Interactive Exercises",
    "MongoDB": "MongoDB University (free courses)",
    "Git": "Git & GitHub Crash Course on freeCodeCamp",
    "Terraform": "HashiCorp Learn — Terraform Tutorials",
    "Ansible": "Ansible Getting Started Guide (docs.ansible.com)",
    "CI/CD": "GitHub Actions Documentation & Tutorials",
    "REST API": "MDN Web Docs — HTTP & REST basics",
    "GraphQL": "How to GraphQL — Free Full-stack Tutorial",
    "Linux": "Linux Journey (linuxjourney.com)",
    "Django": "Django Official Tutorial (djangoproject.com)",
    "Flask": "Flask Mega Tutorial by Miguel Grinberg",
    "FastAPI": "FastAPI Official Tutorial (fastapi.tiangolo.com)",
    "Pandas": "Kaggle — Pandas Course (free)",
    "NumPy": "NumPy Official Absolute Beginner Tutorial",
    "NLP": "Hugging Face NLP Course (free)",
    "Data Science": "IBM Data Science Professional Certificate",
}


def _generate_suggestions(skill_gaps: List[str]) -> List[Dict[str, str]]:
    """Generate learning suggestions for skill gaps."""
    suggestions = []
    for skill in skill_gaps[:8]:  # Limit to top 8
        resource = LEARNING_RESOURCES.get(skill, f"Search for '{skill} tutorial' on YouTube/Coursera")
        suggestions.append({
            "skill": skill,
            "resource": resource,
        })
    return suggestions


# ==================== HELPER FUNCTIONS ====================

def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = np.dot(vec_a, vec_b)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _get_match_level(score: float) -> str:
    """Convert match score to human-readable level."""
    if score >= 80:
        return "Excellent Match"
    elif score >= 65:
        return "Good Match"
    elif score >= 50:
        return "Moderate Match"
    elif score >= 35:
        return "Partial Match"
    else:
        return "Low Match"


def _build_candidate_text(candidate: Dict) -> str:
    """Build a text representation of a candidate for embedding."""
    parts = [
        candidate.get("candidate_summary", ""),
        candidate.get("specialization", ""),
        candidate.get("experience_level", ""),
        " ".join(candidate.get("technologies", [])),
        " ".join(candidate.get("certifications", [])),
        " ".join(candidate.get("notable_achievements", [])),
        candidate.get("education", ""),
    ]
    return " ".join(p for p in parts if p)


def _compute_section_scores(
    model: SentenceTransformer,
    resume_text: str,
    job_description: str,
) -> Dict[str, float]:
    """
    Compute similarity scores for different resume sections.
    Provides a breakdown of which areas match well.
    """
    # Define JD aspects to check
    aspects = {
        "Technical Skills": "programming languages frameworks tools technologies",
        "Experience": "years of experience work history professional background",
        "Education": "degree university college education academic",
        "Projects": "projects portfolio implementations built developed",
    }

    scores = {}
    jd_embedding = model.encode([job_description])[0]

    for aspect_name, aspect_keywords in aspects.items():
        # Find relevant lines from resume
        relevant_lines = []
        for line in resume_text.split('\n'):
            if any(kw in line.lower() for kw in aspect_keywords.split()):
                relevant_lines.append(line)

        if relevant_lines:
            section_text = " ".join(relevant_lines)
            section_embedding = model.encode([section_text])[0]
            sim = _cosine_similarity(section_embedding, jd_embedding)
            scores[aspect_name] = round(float(sim) * 100, 1)
        else:
            scores[aspect_name] = 0.0

    return scores
