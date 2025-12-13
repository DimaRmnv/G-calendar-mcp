"""
Database management for time tracking.

SQLite database schema and operations for projects, phases, tasks, norms, and settings.
Database location: ~/.mcp/gcalendar/time_tracking.db
"""

import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager
from datetime import datetime

from gcalendar_mcp.utils.config import get_app_dir


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
    """Initialize database with schema."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Projects table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                code TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                is_billable INTEGER NOT NULL DEFAULT 0,
                position TEXT,
                structure_level INTEGER NOT NULL DEFAULT 3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Phases table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_code TEXT NOT NULL,
                phase_code TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_code) REFERENCES projects(code) ON DELETE CASCADE,
                UNIQUE(project_code, phase_code)
            )
        """)
        
        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_code TEXT NOT NULL,
                task_code TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_code) REFERENCES projects(code) ON DELETE CASCADE,
                UNIQUE(project_code, task_code)
            )
        """)
        
        # Workday norms table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workday_norms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                norm_hours INTEGER NOT NULL,
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
        
        # Settings table (key-value)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_phases_project ON phases(project_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_norms_year_month ON workday_norms(year, month)")
        
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

def create_project(
    code: str,
    description: str,
    is_billable: bool = False,
    position: Optional[str] = None,
    structure_level: int = 3
) -> dict:
    """Create a new project."""
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
            "code": code.upper(),
            "description": description,
            "is_billable": is_billable,
            "position": position,
            "structure_level": structure_level
        }


def get_project(code: str) -> Optional[dict]:
    """Get project by code."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE code = ?", (code.upper(),))
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["is_billable"] = bool(result["is_billable"])
            return result
        return None


def list_projects(billable_only: bool = False) -> list[dict]:
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


def update_project(code: str, **kwargs) -> Optional[dict]:
    """Update project fields."""
    allowed_fields = {"description", "is_billable", "position", "structure_level"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}
    
    if not updates:
        return get_project(code)
    
    if "is_billable" in updates:
        updates["is_billable"] = int(updates["is_billable"])
    
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [code.upper()]
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE projects SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE code = ?",
            values
        )
        if cursor.rowcount == 0:
            return None
        return get_project(code)


def delete_project(code: str) -> bool:
    """Delete project and associated phases/tasks (cascading)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE code = ?", (code.upper(),))
        return cursor.rowcount > 0


# =============================================================================
# Phases CRUD
# =============================================================================

def create_phase(project_code: str, phase_code: str, description: Optional[str] = None) -> dict:
    """Create a new phase for a project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO phases (project_code, phase_code, description) VALUES (?, ?, ?)",
            (project_code.upper(), phase_code.upper(), description)
        )
        return {
            "id": cursor.lastrowid,
            "project_code": project_code.upper(),
            "phase_code": phase_code.upper(),
            "description": description
        }


def get_phase(project_code: str, phase_code: str) -> Optional[dict]:
    """Get phase by project and phase code."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM phases WHERE project_code = ? AND phase_code = ?",
            (project_code.upper(), phase_code.upper())
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_phases(project_code: Optional[str] = None) -> list[dict]:
    """List phases, optionally filtered by project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_code:
            cursor.execute(
                "SELECT * FROM phases WHERE project_code = ? ORDER BY phase_code",
                (project_code.upper(),)
            )
        else:
            cursor.execute("SELECT * FROM phases ORDER BY project_code, phase_code")
        return [dict(row) for row in cursor.fetchall()]


def update_phase(project_code: str, phase_code: str, description: str) -> Optional[dict]:
    """Update phase description."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE phases SET description = ? WHERE project_code = ? AND phase_code = ?",
            (description, project_code.upper(), phase_code.upper())
        )
        if cursor.rowcount == 0:
            return None
        return get_phase(project_code, phase_code)


def delete_phase(project_code: str, phase_code: str) -> bool:
    """Delete a phase."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM phases WHERE project_code = ? AND phase_code = ?",
            (project_code.upper(), phase_code.upper())
        )
        return cursor.rowcount > 0


# =============================================================================
# Tasks CRUD
# =============================================================================

def create_task(project_code: str, task_code: str, description: Optional[str] = None) -> dict:
    """Create a new task for a project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (project_code, task_code, description) VALUES (?, ?, ?)",
            (project_code.upper(), task_code.upper(), description)
        )
        return {
            "id": cursor.lastrowid,
            "project_code": project_code.upper(),
            "task_code": task_code.upper(),
            "description": description
        }


def get_task(project_code: str, task_code: str) -> Optional[dict]:
    """Get task by project and task code."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE project_code = ? AND task_code = ?",
            (project_code.upper(), task_code.upper())
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_tasks(project_code: Optional[str] = None) -> list[dict]:
    """List tasks, optionally filtered by project."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_code:
            cursor.execute(
                "SELECT * FROM tasks WHERE project_code = ? ORDER BY task_code",
                (project_code.upper(),)
            )
        else:
            cursor.execute("SELECT * FROM tasks ORDER BY project_code, task_code")
        return [dict(row) for row in cursor.fetchall()]


def update_task(project_code: str, task_code: str, description: str) -> Optional[dict]:
    """Update task description."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET description = ? WHERE project_code = ? AND task_code = ?",
            (description, project_code.upper(), task_code.upper())
        )
        if cursor.rowcount == 0:
            return None
        return get_task(project_code, task_code)


def delete_task(project_code: str, task_code: str) -> bool:
    """Delete a task."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM tasks WHERE project_code = ? AND task_code = ?",
            (project_code.upper(), task_code.upper())
        )
        return cursor.rowcount > 0


# =============================================================================
# Workday Norms CRUD
# =============================================================================

def set_norm(year: int, month: int, norm_hours: int) -> dict:
    """Set workday norm for a month (insert or update)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO workday_norms (year, month, norm_hours)
            VALUES (?, ?, ?)
            ON CONFLICT(year, month) DO UPDATE SET norm_hours = excluded.norm_hours
            """,
            (year, month, norm_hours)
        )
        return {"year": year, "month": month, "norm_hours": norm_hours}


def get_norm(year: int, month: int) -> Optional[dict]:
    """Get workday norm for a specific month."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM workday_norms WHERE year = ? AND month = ?",
            (year, month)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_norms(year: Optional[int] = None) -> list[dict]:
    """List workday norms, optionally filtered by year."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if year:
            cursor.execute(
                "SELECT * FROM workday_norms WHERE year = ? ORDER BY month",
                (year,)
            )
        else:
            cursor.execute("SELECT * FROM workday_norms ORDER BY year DESC, month")
        return [dict(row) for row in cursor.fetchall()]


def delete_norm(year: int, month: int) -> bool:
    """Delete workday norm."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM workday_norms WHERE year = ? AND month = ?",
            (year, month)
        )
        return cursor.rowcount > 0


# =============================================================================
# Exclusions CRUD
# =============================================================================

def add_exclusion(pattern: str) -> dict:
    """Add exclusion pattern."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO exclusions (pattern) VALUES (?)",
            (pattern,)
        )
        return {"pattern": pattern, "created": cursor.rowcount > 0}


def list_exclusions() -> list[dict]:
    """List all exclusion patterns."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM exclusions ORDER BY pattern")
        return [dict(row) for row in cursor.fetchall()]


def delete_exclusion(pattern: str) -> bool:
    """Delete exclusion pattern."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM exclusions WHERE pattern = ?", (pattern,))
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

def get_setting(key: str) -> Optional[str]:
    """Get setting value by key."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> dict:
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


def get_all_settings() -> dict[str, str]:
    """Get all settings as dictionary."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in cursor.fetchall()}


# =============================================================================
# Utility functions
# =============================================================================

def get_project_with_details(code: str) -> Optional[dict]:
    """Get project with its phases and tasks."""
    project = get_project(code)
    if not project:
        return None
    
    project["phases"] = list_phases(code)
    project["tasks"] = list_tasks(code)
    return project


def validate_event_components(
    project_code: str,
    phase_code: Optional[str] = None,
    task_code: Optional[str] = None
) -> dict:
    """
    Validate project/phase/task codes against database.
    Returns validation result with details.
    """
    result = {
        "valid": True,
        "project_valid": False,
        "phase_valid": None,
        "task_valid": None,
        "project": None,
        "errors": []
    }
    
    # Check project
    project = get_project(project_code)
    if project:
        result["project_valid"] = True
        result["project"] = project
    else:
        result["valid"] = False
        result["errors"].append(f"Project code '{project_code}' not found")
        return result
    
    # Check phase if provided
    if phase_code:
        phase = get_phase(project_code, phase_code)
        if phase:
            result["phase_valid"] = True
        else:
            result["phase_valid"] = False
            result["valid"] = False
            result["errors"].append(f"Phase '{phase_code}' not found for project '{project_code}'")
    
    # Check task if provided
    if task_code:
        task = get_task(project_code, task_code)
        if task:
            result["task_valid"] = True
        else:
            result["task_valid"] = False
            result["valid"] = False
            result["errors"].append(f"Task '{task_code}' not found for project '{project_code}'")
    
    return result
