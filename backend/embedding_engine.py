"""
Embedding Engine — Semantic Resume-Job Matching
Uses sentence-transformers to create embeddings and compute similarity.
Also performs skill gap analysis and suggests learning resources.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from sentence_transformers import SentenceTransformer

# ==================== MODEL LOADING ====================
# all-MiniLM-L6-v2: fast, lightweight (~80MB), 384-dim vectors
# Downloads automatically on first use, then cached locally

_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    """Lazy-load the sentence-transformer model."""
    global _model
    if _model is None:
        print("[Embedding Engine] Loading sentence-transformers model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[Embedding Engine] Model loaded successfully.")
    return _model


# ==================== CORE MATCHING ====================

def compute_job_match(resume_text: str, job_description: str) -> Dict:
    """
    Compute semantic similarity between resume and job description.
    
    Args:
        resume_text: Full resume text.
        job_description: Job description text.
    
    Returns:
        Dictionary with match_score, skill_gaps, and suggestions.
    """
    model = _get_model()

    # Encode both texts into vectors
    embeddings = model.encode([resume_text, job_description])
    resume_vec = embeddings[0]
    jd_vec = embeddings[1]

    # Cosine similarity
    similarity = _cosine_similarity(resume_vec, jd_vec)
    match_score = round(float(similarity) * 100, 1)  # 0-100%

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
) -> List[Dict]:
    """
    Rank multiple candidates against a job description.
    
    Args:
        candidates: List of candidate dictionaries (with resume_text or technologies).
        job_description: Job description text.
    
    Returns:
        Candidates list sorted by match score (highest first).
    """
    model = _get_model()
    jd_embedding = model.encode([job_description])[0]

    results = []
    for candidate in candidates:
        # Use candidate summary + technologies for matching
        candidate_text = _build_candidate_text(candidate)
        cand_embedding = model.encode([candidate_text])[0]

        similarity = _cosine_similarity(cand_embedding, jd_embedding)
        match_score = round(float(similarity) * 100, 1)

        candidate_result = dict(candidate)
        candidate_result["job_match_score"] = match_score
        candidate_result["match_level"] = _get_match_level(match_score)

        # Skill gap for this candidate
        skill_gaps = _find_skill_gaps(candidate_text, job_description)
        candidate_result["skill_gaps"] = skill_gaps
        candidate_result["suggestions"] = _generate_suggestions(skill_gaps)

        results.append(candidate_result)

    # Sort by match score descending
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
