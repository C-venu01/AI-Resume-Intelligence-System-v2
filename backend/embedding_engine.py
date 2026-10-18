"""
Embedding Engine — Semantic Resume-Job Matching
Uses sentence-transformers to create embeddings and compute similarity.
Also performs skill gap analysis and suggests learning resources.

Falls back to keyword-overlap matching if sentence-transformers is unavailable.
"""

import threading
import re
from typing import Dict, List, Tuple, Optional

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)

# ==================== MODEL LOADING ====================
# Try to import sentence-transformers; fall back to keyword matching if unavailable

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning(
        "sentence-transformers not available. "
        "Job matching will use keyword-overlap instead of semantic similarity."
    )

_model = None
_model_lock = threading.Lock()
_model_load_error: Optional[str] = None


class ModelUnavailableError(RuntimeError):
    """Raised when the embedding model could not be loaded or used."""


def _get_model():
    """
    Lazy-load and cache the sentence-transformer model (thread-safe).
    Returns None if embeddings are not available.
    """
    global _model, _model_load_error

    if not EMBEDDINGS_AVAILABLE:
        return None

    if _model is not None:
        return _model

    with _model_lock:
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
    if not EMBEDDINGS_AVAILABLE:
        return True  # Keyword fallback is always ready
    return _model is not None


# ==================== KEYWORD FALLBACK ====================

def _extract_keywords(text: str) -> set:
    """Extract meaningful keywords from text for overlap matching."""
    text_lower = text.lower()
    # Remove common stop words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
        'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
        'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its',
        'our', 'their', 'what', 'which', 'who', 'whom', 'when', 'where', 'why',
        'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
        'some', 'such', 'no', 'not', 'only', 'own', 'same', 'so', 'than',
        'too', 'very', 'just', 'because', 'as', 'if', 'then', 'else', 'while',
        'about', 'between', 'through', 'during', 'before', 'after', 'above',
        'below', 'from', 'up', 'down', 'out', 'off', 'over', 'under', 'again',
        'further', 'also', 'work', 'working', 'experience', 'years', 'year',
        'including', 'using', 'used', 'use', 'able', 'etc', 'well',
    }
    # Tokenize: keep alphanumeric + common tech chars
    words = re.findall(r'[a-z][a-z0-9+#.]*(?:\.[a-z0-9]+)*', text_lower)
    return {w for w in words if w not in stop_words and len(w) > 1}


def _keyword_match_score(resume_text: str, job_description: str) -> float:
    """Compute match score using keyword overlap (Jaccard-like)."""
    resume_kw = _extract_keywords(resume_text)
    jd_kw = _extract_keywords(job_description)

    if not jd_kw:
        return 0.0

    # How many JD keywords appear in the resume
    overlap = resume_kw & jd_kw
    # Weighted: coverage of JD keywords (more important) + Jaccard
    coverage = len(overlap) / len(jd_kw) if jd_kw else 0
    jaccard = len(overlap) / len(resume_kw | jd_kw) if (resume_kw | jd_kw) else 0

    # Blend: 70% coverage of JD, 30% Jaccard
    score = (0.7 * coverage + 0.3 * jaccard) * 100
    return round(min(score, 100.0), 1)


# ==================== CORE MATCHING ====================

def compute_job_match(resume_text: str, job_description: str) -> Dict:
    """
    Compute similarity between resume and job description.
    Uses semantic embeddings if available, otherwise keyword overlap.
    """
    resume_text = (resume_text or "").strip()
    job_description = (job_description or "").strip()

    if not resume_text:
        raise ValueError("Resume text is empty")
    if not job_description:
        raise ValueError("Job description is empty")

    model = _get_model()

    if model is not None and EMBEDDINGS_AVAILABLE:
        # Semantic matching
        embeddings = model.encode([resume_text, job_description])
        resume_vec = embeddings[0]
        jd_vec = embeddings[1]

        similarity = max(-1.0, min(1.0, _cosine_similarity(resume_vec, jd_vec)))
        match_score = round(max(0.0, similarity) * 100, 1)
        section_scores = _compute_section_scores(model, resume_text, job_description)
    else:
        # Keyword fallback
        match_score = _keyword_match_score(resume_text, job_description)
        section_scores = _compute_section_scores_keyword(resume_text, job_description)

    skill_gaps = _find_skill_gaps(resume_text, job_description)
    suggestions = _generate_suggestions(skill_gaps)

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
    model=None,
) -> List[Dict]:
    """
    Rank multiple candidates against a job description.
    Uses embeddings if available, otherwise keyword overlap.
    """
    job_description = (job_description or "").strip()
    if not job_description:
        raise ValueError("Job description is empty")

    if not candidates:
        return []

    model = model or _get_model()

    if model is not None and EMBEDDINGS_AVAILABLE:
        return _rank_with_embeddings(candidates, job_description, model)
    else:
        return _rank_with_keywords(candidates, job_description)


def _rank_with_embeddings(candidates, job_description, model):
    """Rank candidates using semantic embeddings."""
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

        skill_gaps = _find_skill_gaps(candidate_text, job_description)
        candidate_result["skill_gaps"] = skill_gaps
        candidate_result["suggestions"] = _generate_suggestions(skill_gaps)

        results.append(candidate_result)

    results.sort(key=lambda x: x["job_match_score"], reverse=True)
    return results


def _rank_with_keywords(candidates, job_description):
    """Rank candidates using keyword overlap (fallback)."""
    results = []
    for candidate in candidates:
        candidate_text = _build_candidate_text(candidate)
        match_score = _keyword_match_score(candidate_text, job_description)

        candidate_result = dict(candidate)
        candidate_result["job_match_score"] = match_score
        candidate_result["match_level"] = _get_match_level(match_score)

        skill_gaps = _find_skill_gaps(candidate_text, job_description)
        candidate_result["skill_gaps"] = skill_gaps
        candidate_result["suggestions"] = _generate_suggestions(skill_gaps)

        results.append(candidate_result)

    results.sort(key=lambda x: x["job_match_score"], reverse=True)
    return results


# ==================== SKILL GAP ANALYSIS ====================

def _find_skill_gaps(resume_text: str, job_description: str) -> List[str]:
    """
    Identify skills mentioned in job description but missing from resume.
    """
    from resume_analyzer import TECH_DATABASE

    jd_lower = job_description.lower()
    resume_lower = resume_text.lower()

    gaps = []
    for tech, keywords in TECH_DATABASE.items():
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
    for skill in skill_gaps[:8]:
        resource = LEARNING_RESOURCES.get(skill, f"Search for '{skill} tutorial' on YouTube/Coursera")
        suggestions.append({
            "skill": skill,
            "resource": resource,
        })
    return suggestions


# ==================== HELPER FUNCTIONS ====================

def _cosine_similarity(vec_a, vec_b) -> float:
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


def _compute_section_scores(model, resume_text: str, job_description: str) -> Dict[str, float]:
    """Compute similarity scores for different resume sections using embeddings."""
    aspects = {
        "Technical Skills": "programming languages frameworks tools technologies",
        "Experience": "years of experience work history professional background",
        "Education": "degree university college education academic",
        "Projects": "projects portfolio implementations built developed",
    }

    scores = {}
    jd_embedding = model.encode([job_description])[0]

    for aspect_name, aspect_keywords in aspects.items():
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


def _compute_section_scores_keyword(resume_text: str, job_description: str) -> Dict[str, float]:
    """Compute section scores using keyword overlap (fallback)."""
    aspects = {
        "Technical Skills": "programming languages frameworks tools technologies",
        "Experience": "years of experience work history professional background",
        "Education": "degree university college education academic",
        "Projects": "projects portfolio implementations built developed",
    }

    scores = {}
    for aspect_name, aspect_keywords in aspects.items():
        relevant_lines = []
        for line in resume_text.split('\n'):
            if any(kw in line.lower() for kw in aspect_keywords.split()):
                relevant_lines.append(line)

        if relevant_lines:
            section_text = " ".join(relevant_lines)
            scores[aspect_name] = _keyword_match_score(section_text, job_description)
        else:
            scores[aspect_name] = 0.0

    return scores
