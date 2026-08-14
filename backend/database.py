"""
Database — SQLite Persistent Storage
Stores candidates, job descriptions, and match results.
Auto-creates tables on first run.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


# Database file location (same directory as this script)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume_db.sqlite")


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            linkedin TEXT,
            experience_years INTEGER DEFAULT 0,
            experience_level TEXT,
            specialization TEXT,
            technologies TEXT,          -- JSON array
            certifications TEXT,        -- JSON array
            soft_skills TEXT,           -- JSON array
            education TEXT,
            cgpa REAL,
            projects_count INTEGER DEFAULT 0,
            notable_achievements TEXT,  -- JSON array
            overall_score INTEGER DEFAULT 0,
            candidate_summary TEXT,
            filename TEXT,
            resume_text TEXT,           -- Store full text for re-analysis
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS job_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
            job_id INTEGER REFERENCES job_descriptions(id) ON DELETE CASCADE,
            match_score REAL,
            match_level TEXT,
            skill_gaps TEXT,        -- JSON array
            suggestions TEXT,       -- JSON array
            section_scores TEXT,    -- JSON object
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    conn.commit()
    conn.close()
    print(f"[Database] Initialized at {DB_PATH}")


# ==================== CANDIDATE CRUD ====================

def save_candidate(data: Dict) -> int:
    """
    Save a candidate analysis result to the database.
    Returns the new candidate ID.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO candidates (
            candidate_name, email, phone, linkedin,
            experience_years, experience_level, specialization,
            technologies, certifications, soft_skills,
            education, cgpa, projects_count,
            notable_achievements, overall_score,
            candidate_summary, filename, resume_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("candidate_name", "Unknown"),
        data.get("email", ""),
        data.get("phone", ""),
        data.get("linkedin", ""),
        data.get("experience_years", 0),
        data.get("experience_level", ""),
        data.get("specialization", ""),
        json.dumps(data.get("technologies", [])),
        json.dumps(data.get("certifications", [])),
        json.dumps(data.get("soft_skills", [])),
        data.get("education", ""),
        data.get("cgpa"),
        data.get("projects_count", 0),
        json.dumps(data.get("notable_achievements", [])),
        data.get("overall_score", 0),
        data.get("candidate_summary", ""),
        data.get("filename", ""),
        data.get("resume_text", ""),
    ))

    candidate_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return candidate_id


def get_all_candidates(
    search: str = "",
    sort_by: str = "overall_score",
    sort_order: str = "desc",
    min_score: int = 0,
    experience_level: str = "",
) -> List[Dict]:
    """
    Get all candidates with optional filtering and sorting.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM candidates WHERE overall_score >= ?"
    params: list = [min_score]

    if search:
        query += " AND (candidate_name LIKE ? OR specialization LIKE ? OR technologies LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    if experience_level:
        query += " AND experience_level = ?"
        params.append(experience_level)

    # Validate sort column
    valid_sorts = ["overall_score", "candidate_name", "experience_years", "created_at"]
    if sort_by not in valid_sorts:
        sort_by = "overall_score"

    order = "DESC" if sort_order.lower() == "desc" else "ASC"
    query += f" ORDER BY {sort_by} {order}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_dict(row) for row in rows]


def get_candidate(candidate_id: int) -> Optional[Dict]:
    """Get a single candidate by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def delete_candidate(candidate_id: int) -> bool:
    """Delete a candidate by ID. Returns True if deleted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def delete_all_candidates() -> int:
    """Delete all candidates. Returns count deleted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM candidates")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


# ==================== JOB DESCRIPTION CRUD ====================

def save_job_description(title: str, description: str) -> int:
    """Save a job description. Returns the new ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO job_descriptions (title, description) VALUES (?, ?)",
        (title, description)
    )
    jd_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jd_id


def get_job_descriptions() -> List[Dict]:
    """Get all saved job descriptions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM job_descriptions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ==================== MATCH RESULTS ====================

def save_match_result(
    candidate_id: int, job_id: int, match_data: Dict
) -> int:
    """Save a match result."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO match_results (
            candidate_id, job_id, match_score, match_level,
            skill_gaps, suggestions, section_scores
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        candidate_id,
        job_id,
        match_data.get("match_score", 0),
        match_data.get("match_level", ""),
        json.dumps(match_data.get("skill_gaps", [])),
        json.dumps(match_data.get("suggestions", [])),
        json.dumps(match_data.get("section_scores", {})),
    ))
    match_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return match_id


# ==================== STATISTICS ====================

def get_stats() -> Dict:
    """Get dashboard statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    # Total candidates
    cursor.execute("SELECT COUNT(*) FROM candidates")
    stats["total_candidates"] = cursor.fetchone()[0]

    # Average score
    cursor.execute("SELECT AVG(overall_score) FROM candidates")
    avg = cursor.fetchone()[0]
    stats["avg_score"] = round(avg, 1) if avg else 0

    # Top score
    cursor.execute("SELECT MAX(overall_score) FROM candidates")
    top = cursor.fetchone()[0]
    stats["top_score"] = top if top else 0

    # Experience level distribution
    cursor.execute("""
        SELECT experience_level, COUNT(*) as count
        FROM candidates
        GROUP BY experience_level
    """)
    stats["experience_distribution"] = {
        row["experience_level"]: row["count"]
        for row in cursor.fetchall()
    }

    # Top technologies
    cursor.execute("SELECT technologies FROM candidates")
    tech_count: Dict[str, int] = {}
    for row in cursor.fetchall():
        techs = json.loads(row["technologies"])
        for tech in techs:
            tech_count[tech] = tech_count.get(tech, 0) + 1

    stats["top_technologies"] = dict(
        sorted(tech_count.items(), key=lambda x: x[1], reverse=True)[:10]
    )

    # Specialization distribution
    cursor.execute("""
        SELECT specialization, COUNT(*) as count
        FROM candidates
        GROUP BY specialization
        ORDER BY count DESC
    """)
    stats["specialization_distribution"] = {
        row["specialization"]: row["count"]
        for row in cursor.fetchall()
    }

    conn.close()
    return stats


# ==================== HELPERS ====================

def _row_to_dict(row: sqlite3.Row) -> Dict:
    """Convert a database row to a dictionary, parsing JSON fields."""
    d = dict(row)
    # Parse JSON fields
    for field in ["technologies", "certifications", "soft_skills", "notable_achievements"]:
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
    # Remove resume_text from list responses (too large)
    d.pop("resume_text", None)
    return d


# Initialize database on module import
init_db()
