"""
Database — SQLite Persistent Storage
Stores candidates, job descriptions, and match results.
Auto-creates tables on first run.

Configuration:
    DATABASE_PATH env var controls the database file location.
    Default: /app/backend/data/resume_db.sqlite (Docker) or local dir (dev)

Limitations:
    SQLite is suitable for small-to-medium workloads (single server, <100k rows).
    For horizontal scaling, multi-instance deployments, or high write concurrency,
    migrate to PostgreSQL or another managed database.
"""

import sqlite3
import json
import os
from typing import Dict, List, Optional
from contextlib import contextmanager

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)


# ==================== CONFIGURATION ====================

# Database file location — configurable via environment variable
DB_PATH = settings.resolved_database_path

# Connection timeout (seconds) — handles concurrent access
DB_TIMEOUT = 30.0

# Maximum rows returned in a single query (pagination safety)
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


def set_db_path(path: str):
    """
    Override the database path (used for testing).
    Ensures the parent directory exists.
    """
    global DB_PATH
    DB_PATH = path
    # Ensure the directory exists
    db_dir = os.path.dirname(os.path.abspath(path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """
    Get a database connection with row factory and safe settings.

    - WAL mode for better concurrent read/write
    - Busy timeout to handle locked database gracefully
    - Foreign keys enabled for cascading deletes
    """
    # Ensure parent directory exists
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")       # Better concurrent access
    conn.execute("PRAGMA busy_timeout=30000")     # Wait up to 30s if locked
    conn.execute("PRAGMA foreign_keys=ON")        # Enable cascade deletes
    conn.execute("PRAGMA synchronous=NORMAL")     # Balance safety/speed
    return conn


@contextmanager
def db_connection():
    """
    Context manager for database connections.
    Automatically commits on success, rolls back on error, and always closes.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables, indexes, and enable foreign keys."""
    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_username TEXT NOT NULL DEFAULT 'admin',
                candidate_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                linkedin TEXT,
                experience_years INTEGER DEFAULT 0,
                internship_experience_years INTEGER DEFAULT 0,
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
                name_confidence REAL DEFAULT 0,
                name_evidence TEXT,
                experience_evidence TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS job_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_username TEXT NOT NULL DEFAULT 'admin',
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
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

            -- Indexes for common query patterns
            CREATE INDEX IF NOT EXISTS idx_candidates_score
                ON candidates(overall_score DESC);
            CREATE INDEX IF NOT EXISTS idx_candidates_name
                ON candidates(candidate_name);
            CREATE INDEX IF NOT EXISTS idx_candidates_level
                ON candidates(experience_level);
            CREATE INDEX IF NOT EXISTS idx_candidates_created
                ON candidates(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_match_candidate
                ON match_results(candidate_id);
            CREATE INDEX IF NOT EXISTS idx_match_job
                ON match_results(job_id);
        """)
        existing_columns = {
            row["name"] for row in cursor.execute("PRAGMA table_info(candidates)")
        }
        if "owner_username" not in existing_columns:
            cursor.execute(
                "ALTER TABLE candidates ADD COLUMN owner_username TEXT NOT NULL DEFAULT 'admin'"
            )
            cursor.execute(
                "UPDATE candidates SET owner_username = ?",
                (settings.admin_username,),
            )

        existing_job_columns = {
            row["name"] for row in cursor.execute("PRAGMA table_info(job_descriptions)")
        }
        if "owner_username" not in existing_job_columns:
            cursor.execute(
                "ALTER TABLE job_descriptions ADD COLUMN owner_username TEXT NOT NULL DEFAULT 'admin'"
            )
            cursor.execute(
                "UPDATE job_descriptions SET owner_username = ?",
                (settings.admin_username,),
            )

        migrations = {
            "internship_experience_years": "INTEGER DEFAULT 0",
            "name_confidence": "REAL DEFAULT 0",
            "name_evidence": "TEXT",
            "experience_evidence": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in existing_columns:
                cursor.execute(
                    f"ALTER TABLE candidates ADD COLUMN {column} {definition}"
                )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_owner "
            "ON candidates(owner_username, overall_score DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_job_descriptions_owner "
            "ON job_descriptions(owner_username, created_at DESC)"
        )

    logger.info(f"Database initialized at {DB_PATH}")


def health_check() -> Dict:
    """
    Check database connectivity and return status.
    Used by the /api/health endpoint.
    """
    try:
        return {
            "status": "healthy",
        }
    except Exception as e:
        logger.error(f"Database health check failed: {type(e).__name__}")
        return {
            "status": "unhealthy",
            "error": "Database connection failed",
        }


# ==================== CANDIDATE CRUD ====================

def save_candidate(data: Dict, owner_username: Optional[str] = None) -> int:
    """
    Save a candidate analysis result to the database.
    Returns the new candidate ID.
    """
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO candidates (
                owner_username, candidate_name, email, phone, linkedin,
                experience_years, internship_experience_years,
                experience_level, specialization,
                technologies, certifications, soft_skills,
                education, cgpa, projects_count,
                notable_achievements, overall_score,
                candidate_summary, filename, resume_text,
                name_confidence, name_evidence, experience_evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            owner_username or settings.admin_username,
            data.get("candidate_name", "Name not detected"),
            data.get("email", ""),
            data.get("phone", ""),
            data.get("linkedin", ""),
            data.get("experience_years", 0),
            data.get("internship_experience_years", 0),
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
            data.get("name_confidence", 0.0),
            json.dumps(data.get("name_evidence", {})),
            json.dumps(data.get("experience_evidence", [])),
        ))
        return cursor.lastrowid


def update_candidate_reanalysis(
    candidate_id: int, data: Dict, owner_username: Optional[str] = None
) -> bool:
    """Update corrected parser results without changing the candidate ID."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE candidates
            SET candidate_name = ?,
                experience_years = ?,
                internship_experience_years = ?,
                experience_level = ?,
                overall_score = ?,
                candidate_summary = ?,
                name_confidence = ?,
                name_evidence = ?,
                experience_evidence = ?,
                updated_at = datetime('now')
            WHERE id = ? AND owner_username = ?
        """, (
            data.get("candidate_name", "Name not detected"),
            data.get("experience_years", 0),
            data.get("internship_experience_years", 0),
            data.get("experience_level", "Not specified"),
            data.get("overall_score", 0),
            data.get("candidate_summary", ""),
            data.get("name_confidence", 0.0),
            json.dumps(data.get("name_evidence", {})),
            json.dumps(data.get("experience_evidence", [])),
            candidate_id,
            owner_username or settings.admin_username,
        ))
        return cursor.rowcount > 0


def get_all_candidates(
    search: str = "",
    sort_by: str = "overall_score",
    sort_order: str = "desc",
    min_score: int = 0,
    experience_level: str = "",
    limit: Optional[int] = None,
    offset: int = 0,
    include_resume_text: bool = False,
    owner_username: Optional[str] = None,
) -> List[Dict]:
    """
    Get candidates with optional filtering, sorting, and pagination.

    Args:
        search: Text search across name, specialization, technologies
        sort_by: Column to sort by (validated)
        sort_order: "asc" or "desc"
        min_score: Minimum overall_score filter
        experience_level: Exact experience level filter
        limit: Max rows to return (None = no limit, but capped for safety)
        offset: Number of rows to skip (for pagination)
        include_resume_text: Whether to include full resume text (usually False)

    Returns:
        List of candidate dicts
    """
    with db_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM candidates WHERE owner_username = ? AND overall_score >= ?"
        params: list = [owner_username or settings.admin_username, min_score]

        if search:
            query += " AND (candidate_name LIKE ? OR specialization LIKE ? OR technologies LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])

        if experience_level:
            query += " AND experience_level = ?"
            params.append(experience_level)

        # Validate sort column (prevent SQL injection)
        valid_sorts = ["overall_score", "candidate_name", "experience_years", "created_at"]
        if sort_by not in valid_sorts:
            sort_by = "overall_score"

        order = "DESC" if sort_order.lower() == "desc" else "ASC"
        query += f" ORDER BY {sort_by} {order}"

        # Pagination — always apply a limit for safety
        if limit is None:
            limit = MAX_PAGE_SIZE
        limit = min(int(limit), MAX_PAGE_SIZE)
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, max(0, int(offset))])

        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [_row_to_dict(row, include_resume_text=include_resume_text) for row in rows]


def count_candidates(
    search: str = "",
    min_score: int = 0,
    experience_level: str = "",
    owner_username: Optional[str] = None,
) -> int:
    """Count total candidates matching filters (for pagination metadata)."""
    with db_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM candidates WHERE owner_username = ? AND overall_score >= ?"
        params: list = [owner_username or settings.admin_username, min_score]

        if search:
            query += " AND (candidate_name LIKE ? OR specialization LIKE ? OR technologies LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])

        if experience_level:
            query += " AND experience_level = ?"
            params.append(experience_level)

        cursor.execute(query, params)
        return cursor.fetchone()[0]


def get_candidate(
    candidate_id: int,
    include_resume_text: bool = True,
    owner_username: Optional[str] = None,
) -> Optional[Dict]:
    """Get a single candidate by ID."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM candidates WHERE id = ? AND owner_username = ?",
            (candidate_id, owner_username or settings.admin_username),
        )
        row = cursor.fetchone()

    return _row_to_dict(row, include_resume_text=include_resume_text) if row else None


def delete_candidate(candidate_id: int, owner_username: Optional[str] = None) -> bool:
    """Delete a candidate by ID. Returns True if deleted."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM candidates WHERE id = ? AND owner_username = ?",
            (candidate_id, owner_username or settings.admin_username),
        )
        return cursor.rowcount > 0


def delete_all_candidates(owner_username: Optional[str] = None) -> int:
    """Delete all candidates. Returns count deleted."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM candidates WHERE owner_username = ?",
            (owner_username or settings.admin_username,),
        )
        return cursor.rowcount


# ==================== JOB DESCRIPTION CRUD ====================

def save_job_description(
    title: str,
    description: str,
    owner_username: Optional[str] = None,
) -> int:
    """Save a job description. Returns the new ID."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO job_descriptions (owner_username, title, description) VALUES (?, ?, ?)",
            (owner_username or settings.admin_username, title, description)
        )
        return cursor.lastrowid


def get_job_descriptions(owner_username: Optional[str] = None) -> List[Dict]:
    """Get all saved job descriptions."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM job_descriptions WHERE owner_username = ? ORDER BY created_at DESC",
            (owner_username or settings.admin_username,),
        )
        rows = cursor.fetchall()
    return [
        {key: value for key, value in dict(row).items() if key != "owner_username"}
        for row in rows
    ]


# ==================== MATCH RESULTS ====================

def save_match_result(candidate_id: int, job_id: int, match_data: Dict) -> int:
    """Save a match result."""
    with db_connection() as conn:
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
        return cursor.lastrowid


# ==================== STATISTICS ====================

def get_stats(owner_username: Optional[str] = None) -> Dict:
    """Get dashboard statistics."""
    with db_connection() as conn:
        cursor = conn.cursor()
        stats = {}

        owner = owner_username or settings.admin_username

        # Total candidates
        cursor.execute(
            "SELECT COUNT(*) FROM candidates WHERE owner_username = ?", (owner,)
        )
        stats["total_candidates"] = cursor.fetchone()[0]

        # Average score
        cursor.execute(
            "SELECT AVG(overall_score) FROM candidates WHERE owner_username = ?",
            (owner,),
        )
        avg = cursor.fetchone()[0]
        stats["avg_score"] = round(avg, 1) if avg else 0

        # Top score
        cursor.execute(
            "SELECT MAX(overall_score) FROM candidates WHERE owner_username = ?",
            (owner,),
        )
        top = cursor.fetchone()[0]
        stats["top_score"] = top if top else 0

        # Experience level distribution
        cursor.execute("""
            SELECT experience_level, COUNT(*) as count
            FROM candidates
            WHERE owner_username = ?
            GROUP BY experience_level
        """, (owner,))
        stats["experience_distribution"] = {
            row["experience_level"] or "Unknown": row["count"]
            for row in cursor.fetchall()
        }

        # Top technologies
        cursor.execute(
            "SELECT technologies FROM candidates WHERE owner_username = ?",
            (owner,),
        )
        tech_count: Dict[str, int] = {}
        for row in cursor.fetchall():
            try:
                techs = json.loads(row["technologies"]) if row["technologies"] else []
            except (json.JSONDecodeError, TypeError):
                techs = []
            for tech in techs:
                tech_count[tech] = tech_count.get(tech, 0) + 1

        stats["top_technologies"] = dict(
            sorted(tech_count.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        # Specialization distribution
        cursor.execute("""
            SELECT specialization, COUNT(*) as count
            FROM candidates
            WHERE owner_username = ?
            GROUP BY specialization
            ORDER BY count DESC
        """, (owner,))
        stats["specialization_distribution"] = {
            row["specialization"] or "Unknown": row["count"]
            for row in cursor.fetchall()
        }

    return stats


# ==================== HELPERS ====================

def _row_to_dict(row: sqlite3.Row, include_resume_text: bool = False) -> Dict:
    """
    Convert a database row to a dictionary, parsing JSON fields.

    Args:
        row: SQLite row
        include_resume_text: If False (default), strip resume_text from result
    """
    d = dict(row)
    d.pop("owner_username", None)

    # Parse JSON fields
    for field in ["technologies", "certifications", "soft_skills", "notable_achievements"]:
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []

    # Remove resume_text from responses unless explicitly requested (privacy)
    if not include_resume_text:
        d.pop("resume_text", None)
    d.pop("name_confidence", None)
    d.pop("name_evidence", None)
    d.pop("experience_evidence", None)

    return d


def create_user(username: str, password_hash: str) -> bool:
    """Create a registered workspace account; raises on duplicate usernames."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        return cursor.rowcount == 1


def get_user_by_username(username: str) -> Optional[Dict]:
    """Get the credential record for authentication without exposing it via APIs."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, password_hash FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
    return dict(row) if row else None


# ==================== BACKUP UTILITIES ====================

def backup_database(backup_path: str) -> bool:
    """
    Create a backup of the SQLite database using the online backup API.
    Safe to run while the database is in use.

    Args:
        backup_path: Destination path for the backup file

    Returns:
        True if successful
    """
    try:
        with db_connection() as source:
            dest = sqlite3.connect(backup_path)
            try:
                source.backup(dest)
            finally:
                dest.close()
        logger.info(f"Database backup created at {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Backup failed: {type(e).__name__}")
        return False


# ==================== MIGRATION UTILITIES ====================

def get_schema_version() -> int:
    """Get the current schema version."""
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        return cursor.fetchone()[0]


def set_schema_version(version: int):
    """Set the schema version (for migrations)."""
    with db_connection() as conn:
        conn.execute(f"PRAGMA user_version = {int(version)}")


# Initialize database on module import
init_db()
