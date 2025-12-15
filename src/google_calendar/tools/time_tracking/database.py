"""
Database management for time tracking.

SQLite database schema and operations for projects, phases, tasks, norms, and settings.
All entities have integer id as primary key for batch operations.
Database location: ~/.mcp/google-calendar/time_tracking.db
"""

import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from google_calendar.utils.config import get_app_dir


DATABASE_NAME = "time_tracking.db"


def get_database_path() -> Path:
    """Get path to time tracking database."""
    return get_app_dir() / DATABASE_NAME


def database_exists() -> bool:
    """Check if database file exists."""
    return get_database_path().exists()


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """Initialize database with schema. All tables have id as primary key."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Projects table - id is PK, code can repeat
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                description TEXT NOT NULL,
                is_billable INTEGER NOT NULL DEFAULT 0,
                position TEXT,
                structure_level INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Phases table - references project by id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, code)
            )
        """)

        # Tasks table - references project by id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, code)
            )
        """)

        # Workday norms table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS norms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                hours REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(year, month)
            )
        """)

        # Exclusions table (event patterns to skip)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exclusions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Settings table (key-value, no id needed)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_phases_project ON phases(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_norms_year_month ON norms(year, month)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_code ON projects(code)")

        # Insert default settings
        default_settings = [
            ("work_calendar", "primary"),
            ("billable_target_type", "percent"),
            ("billable_target_value", "75"),
            ("base_location", ""),
        ]

        for key, value in default_settings:
            cursor.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

        # Insert default exclusions
        default_exclusions = ["Away", "Lunch", "Offline", "Out of office"]
        for pattern in default_exclusions:
            cursor.execute(
                "INSERT OR IGNORE INTO exclusions (pattern) VALUES (?)",
                (pattern,)
            )


def ensure_database() -> bool:
    """Ensure database exists and is initialized. Returns True if newly created."""
    newly_created = not database_exists()
    if newly_created:
        init_database()
    return newly_created


# =============================================================================
# Projects CRUD
# =============================================================================

def project_add(
    code: str,
    description: str,
    is_billable: bool = False,
    position: Optional[str] = None,
    structure_level: int = 1
) -> dict:
    """Create a new project. Returns created project with id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects (code, description, is_billable, position, structure_level)
            VALUES (?, ?, ?, ?, ?)
            """,
            (code.upper(), description, int(is_billable), position, structure_level)
        )
        return {
            "id": cursor.lastrowid,
            "code": code.upper(),
            "description": description,
            "is_billable": is_billable,
            "position": position,
            "structure_level": structure_level
        }


def project_get(id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get project by id or code."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if id is not None:
            cursor.execute("SELECT * FROM projects WHERE id = ?", (id,))
        elif code is not None:
            cursor.execute("SELECT * FROM projects WHERE code = ?", (code.upper(),))
        else:
            return None
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["is_billable"] = bool(result["is_billable"])
            return result
        return None


def project_list(billable_only: bool = False) -> list[dict]:
    """List all projects."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if billable_only:
            cursor.execute("SELECT * FROM projects WHERE is_billable = 1 ORDER BY code")
        else:
            cursor.execute("SELECT * FROM projects ORDER BY code")
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_billable"] = bool(item["is_billable"])
            results.append(item)
        return results


def project_update(id: int, **kwargs) -> Optional[dict]:
    """Update project by id."""
    allowed_fields = {"code", "description", "is_billable", "position", "structure_level"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return project_get(id=id)

    if "is_billable" in updates:
        updates["is_billable"] = int(updates["is_billable"])
    if "code" in updates:
        updates["code"] = updates["code"].upper()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE projects SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        if cursor.rowcount == 0:
            return None
        return project_get(id=id)


def project_delete(id: int) -> bool:
    """Delete project by id (cascades to phases/tasks)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (id,))
        return cursor.rowcount > 0


# =============================================================================
# Phases CRUD
# =============================================================================

def phase_add(project_id: int, code: str, description: Optional[str] = None) -> dict:
    """Create a new phase for a project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO phases (project_id, code, description) VALUES (?, ?, ?)",
            (project_id, code.upper(), description)
        )
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "code": code.upper(),
            "description": description
        }


def phase_get(id: Optional[int] = None, project_id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get phase by id or by project_id + code."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if id is not None:
            cursor.execute("SELECT * FROM phases WHERE id = ?", (id,))
        elif project_id is not None and code is not None:
            cursor.execute(
                "SELECT * FROM phases WHERE project_id = ? AND code = ?",
                (project_id, code.upper())
            )
        else:
            return None
        row = cursor.fetchone()
        return dict(row) if row else None


def phase_list(project_id: Optional[int] = None) -> list[dict]:
    """List phases, optionally filtered by project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_id is not None:
            cursor.execute(
                "SELECT * FROM phases WHERE project_id = ? ORDER BY code",
                (project_id,)
            )
        else:
            cursor.execute("SELECT * FROM phases ORDER BY project_id, code")
        return [dict(row) for row in cursor.fetchall()]


def phase_update(id: int, **kwargs) -> Optional[dict]:
    """Update phase by id."""
    allowed_fields = {"code", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return phase_get(id=id)

    if "code" in updates:
        updates["code"] = updates["code"].upper()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE phases SET {set_clause} WHERE id = ?", values)
        if cursor.rowcount == 0:
            return None
        return phase_get(id=id)


def phase_delete(id: int) -> bool:
    """Delete phase by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM phases WHERE id = ?", (id,))
        return cursor.rowcount > 0


# =============================================================================
# Tasks CRUD
# =============================================================================

def task_add(project_id: int, code: str, description: Optional[str] = None) -> dict:
    """Create a new task for a project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (project_id, code, description) VALUES (?, ?, ?)",
            (project_id, code.upper(), description)
        )
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "code": code.upper(),
            "description": description
        }


def task_get(id: Optional[int] = None, project_id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get task by id or by project_id + code."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if id is not None:
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (id,))
        elif project_id is not None and code is not None:
            cursor.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND code = ?",
                (project_id, code.upper())
            )
        else:
            return None
        row = cursor.fetchone()
        return dict(row) if row else None


def task_list(project_id: Optional[int] = None) -> list[dict]:
    """List tasks, optionally filtered by project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_id is not None:
            cursor.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY code",
                (project_id,)
            )
        else:
            cursor.execute("SELECT * FROM tasks ORDER BY project_id, code")
        return [dict(row) for row in cursor.fetchall()]


def task_update(id: int, **kwargs) -> Optional[dict]:
    """Update task by id."""
    allowed_fields = {"code", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return task_get(id=id)

    if "code" in updates:
        updates["code"] = updates["code"].upper()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        if cursor.rowcount == 0:
            return None
        return task_get(id=id)


def task_delete(id: int) -> bool:
    """Delete task by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (id,))
        return cursor.rowcount > 0


# =============================================================================
# Norms CRUD
# =============================================================================

def norm_add(year: int, month: int, hours: float) -> dict:
    """Add or update workday norm for a month."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO norms (year, month, hours)
            VALUES (?, ?, ?)
            ON CONFLICT(year, month) DO UPDATE SET hours = excluded.hours
            """,
            (year, month, hours)
        )
        # Get the id
        cursor.execute("SELECT id FROM norms WHERE year = ? AND month = ?", (year, month))
        row = cursor.fetchone()
        return {"id": row["id"], "year": year, "month": month, "hours": hours}


def norm_get(id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None) -> Optional[dict]:
    """Get norm by id or by year + month."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if id is not None:
            cursor.execute("SELECT * FROM norms WHERE id = ?", (id,))
        elif year is not None and month is not None:
            cursor.execute("SELECT * FROM norms WHERE year = ? AND month = ?", (year, month))
        else:
            return None
        row = cursor.fetchone()
        return dict(row) if row else None


def norm_list(year: Optional[int] = None) -> list[dict]:
    """List norms, optionally filtered by year."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if year is not None:
            cursor.execute("SELECT * FROM norms WHERE year = ? ORDER BY month", (year,))
        else:
            cursor.execute("SELECT * FROM norms ORDER BY year DESC, month")
        return [dict(row) for row in cursor.fetchall()]


def norm_delete(id: int) -> bool:
    """Delete norm by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM norms WHERE id = ?", (id,))
        return cursor.rowcount > 0


# =============================================================================
# Exclusions CRUD
# =============================================================================

def exclusion_add(pattern: str) -> dict:
    """Add exclusion pattern."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO exclusions (pattern) VALUES (?)",
            (pattern,)
        )
        if cursor.rowcount > 0:
            return {"id": cursor.lastrowid, "pattern": pattern, "created": True}
        # Already exists, get id
        cursor.execute("SELECT id FROM exclusions WHERE pattern = ?", (pattern,))
        row = cursor.fetchone()
        return {"id": row["id"], "pattern": pattern, "created": False}


def exclusion_list() -> list[dict]:
    """List all exclusion patterns."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM exclusions ORDER BY pattern")
        return [dict(row) for row in cursor.fetchall()]


def exclusion_delete(id: int) -> bool:
    """Delete exclusion by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM exclusions WHERE id = ?", (id,))
        return cursor.rowcount > 0


def is_excluded(event_summary: str) -> bool:
    """Check if event summary matches any exclusion pattern (case-insensitive)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pattern FROM exclusions")
        patterns = [row["pattern"].lower() for row in cursor.fetchall()]
        return event_summary.strip().lower() in patterns


# =============================================================================
# Settings CRUD
# =============================================================================

def config_get(key: str) -> Optional[str]:
    """Get setting value by key."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None


def config_set(key: str, value: str) -> dict:
    """Set setting value."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value)
        )
        return {"key": key, "value": value}


def config_list() -> dict[str, str]:
    """Get all settings as dictionary."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in cursor.fetchall()}


# =============================================================================
# Utility functions for parser (lookup by code)
# =============================================================================

def get_project_by_code(code: str) -> Optional[dict]:
    """Get project by code (for parser). Returns first match."""
    return project_get(code=code)


def get_projects_by_code(code: str) -> list[dict]:
    """Get ALL projects with the same code, ordered by structure_level DESC.
    
    This allows multiple projects with same code but different structure levels.
    Example: CAYIB Level 3 (with phases+tasks) and CAYIB Level 2 (phases only).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM projects WHERE code = ? ORDER BY structure_level DESC",
            (code.upper(),)
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_billable"] = bool(item["is_billable"])
            results.append(item)
        return results


def get_phase_by_code(project_code: str, phase_code: str) -> Optional[dict]:
    """Get phase by project code and phase code (for parser)."""
    project = project_get(code=project_code)
    if not project:
        return None
    return phase_get(project_id=project["id"], code=phase_code)


def get_task_by_code(project_code: str, task_code: str) -> Optional[dict]:
    """Get task by project code and task code (for parser)."""
    project = project_get(code=project_code)
    if not project:
        return None
    return task_get(project_id=project["id"], code=task_code)


# Aliases for backward compatibility with parser
get_project = get_project_by_code
get_phase = get_phase_by_code
get_task = get_task_by_code
get_setting = config_get
get_norm = lambda year, month: norm_get(year=year, month=month)
