"""
Async database operations for time tracking (PostgreSQL).

Used in cloud mode with asyncpg connection pool.
Database: google_calendar_mcp (shared with contacts)
"""

from typing import Optional
from google_calendar.db.connection import get_db


# =============================================================================
# Database State
# =============================================================================

async def database_exists() -> bool:
    """Check if time tracking tables exist."""
    try:
        async with get_db() as conn:
            row = await conn.fetchrow("""
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = 'projects'
                )
            """)
            return row[0] if row else False
    except Exception:
        return False


async def ensure_database() -> bool:
    """Ensure database is initialized. Returns True if newly created."""
    from google_calendar.db.connection import ensure_db_initialized
    await ensure_db_initialized()
    return False


# =============================================================================
# Projects CRUD
# =============================================================================

async def project_add(
    code: str,
    description: str,
    is_billable: bool = False,
    is_active: bool = True,
    position: Optional[str] = None,
    structure_level: int = 1
) -> dict:
    """Create a new project. Returns created project with id."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (code, description, is_billable, is_active, position, structure_level)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            code.upper(), description, is_billable, is_active, position, structure_level
        )
        return {
            "id": row["id"],
            "code": code.upper(),
            "description": description,
            "is_billable": is_billable,
            "is_active": is_active,
            "position": position,
            "structure_level": structure_level
        }


async def project_get(id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get project by id or code."""
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", id)
        elif code is not None:
            row = await conn.fetchrow("SELECT * FROM projects WHERE code = $1", code.upper())
        else:
            return None
        if row:
            return dict(row)
        return None


async def project_list(billable_only: bool = False, active_only: bool = False) -> list[dict]:
    """List all projects."""
    async with get_db() as conn:
        conditions = []
        if billable_only:
            conditions.append("is_billable = TRUE")
        if active_only:
            conditions.append("is_active = TRUE")

        query = "SELECT * FROM projects"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY code"

        rows = await conn.fetch(query)
        return [dict(row) for row in rows]


async def project_update(id: int, **kwargs) -> Optional[dict]:
    """Update project by id."""
    allowed_fields = {"code", "description", "is_billable", "is_active", "position", "structure_level"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await project_get(id=id)

    if "code" in updates:
        updates["code"] = updates["code"].upper()

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    values.append(id)

    async with get_db() as conn:
        await conn.execute(
            f"UPDATE projects SET {', '.join(set_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(values)}",
            *values
        )
        return await project_get(id=id)


async def project_delete(id: int) -> bool:
    """Delete project by id (cascades to phases/tasks)."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM projects WHERE id = $1", id)
        return result.split()[-1] != '0'


async def project_list_active() -> list[dict]:
    """Get active projects with their phases and tasks."""
    projects = await project_list(active_only=True)
    for project in projects:
        project["phases"] = await phase_list(project_id=project["id"])
        project["tasks"] = await task_list(project_id=project["id"])
        if project["structure_level"] == 1:
            project["format"] = "PROJECT * Description"
        elif project["structure_level"] == 2:
            project["format"] = "PROJECT * PHASE * Description"
        else:
            project["format"] = "PROJECT * PHASE * TASK * Description"
    return projects


# =============================================================================
# Phases CRUD
# =============================================================================

async def phase_add(project_id: int, code: str, description: Optional[str] = None) -> dict:
    """Create a new phase for a project."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO phases (project_id, code, description) VALUES ($1, $2, $3) RETURNING id",
            project_id, code.upper(), description
        )
        return {
            "id": row["id"],
            "project_id": project_id,
            "code": code.upper(),
            "description": description
        }


async def phase_get(id: Optional[int] = None, project_id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get phase by id or by project_id + code."""
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM phases WHERE id = $1", id)
        elif project_id is not None and code is not None:
            row = await conn.fetchrow(
                "SELECT * FROM phases WHERE project_id = $1 AND code = $2",
                project_id, code.upper()
            )
        else:
            return None
        return dict(row) if row else None


async def phase_list(project_id: Optional[int] = None) -> list[dict]:
    """List phases, optionally filtered by project."""
    async with get_db() as conn:
        if project_id is not None:
            rows = await conn.fetch(
                "SELECT * FROM phases WHERE project_id = $1 ORDER BY code",
                project_id
            )
        else:
            rows = await conn.fetch("SELECT * FROM phases ORDER BY project_id, code")
        return [dict(row) for row in rows]


async def phase_update(id: int, **kwargs) -> Optional[dict]:
    """Update phase by id."""
    allowed_fields = {"code", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await phase_get(id=id)

    if "code" in updates:
        updates["code"] = updates["code"].upper()

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    values.append(id)

    async with get_db() as conn:
        await conn.execute(f"UPDATE phases SET {', '.join(set_parts)} WHERE id = ${len(values)}", *values)
        return await phase_get(id=id)


async def phase_delete(id: int) -> bool:
    """Delete phase by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM phases WHERE id = $1", id)
        return result.split()[-1] != '0'


# =============================================================================
# Tasks CRUD
# =============================================================================

async def task_add(project_id: int, code: str, description: Optional[str] = None) -> dict:
    """Create a new task for a project."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO tasks (project_id, code, description) VALUES ($1, $2, $3) RETURNING id",
            project_id, code.upper(), description
        )
        return {
            "id": row["id"],
            "project_id": project_id,
            "code": code.upper(),
            "description": description
        }


async def task_get(id: Optional[int] = None, project_id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get task by id or by project_id + code."""
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", id)
        elif project_id is not None and code is not None:
            row = await conn.fetchrow(
                "SELECT * FROM tasks WHERE project_id = $1 AND code = $2",
                project_id, code.upper()
            )
        else:
            return None
        return dict(row) if row else None


async def task_list(project_id: Optional[int] = None) -> list[dict]:
    """List tasks, optionally filtered by project."""
    async with get_db() as conn:
        if project_id is not None:
            rows = await conn.fetch(
                "SELECT * FROM tasks WHERE project_id = $1 ORDER BY code",
                project_id
            )
        else:
            rows = await conn.fetch("SELECT * FROM tasks ORDER BY project_id, code")
        return [dict(row) for row in rows]


async def task_update(id: int, **kwargs) -> Optional[dict]:
    """Update task by id."""
    allowed_fields = {"code", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await task_get(id=id)

    if "code" in updates:
        updates["code"] = updates["code"].upper()

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    values.append(id)

    async with get_db() as conn:
        await conn.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ${len(values)}", *values)
        return await task_get(id=id)


async def task_delete(id: int) -> bool:
    """Delete task by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM tasks WHERE id = $1", id)
        return result.split()[-1] != '0'


# =============================================================================
# Norms CRUD
# =============================================================================

async def norm_add(year: int, month: int, hours: float) -> dict:
    """Add or update workday norm for a month."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO norms (year, month, hours)
            VALUES ($1, $2, $3)
            ON CONFLICT(year, month) DO UPDATE SET hours = EXCLUDED.hours
            RETURNING id
            """,
            year, month, hours
        )
        return {"id": row["id"], "year": year, "month": month, "hours": hours}


async def norm_get(id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None) -> Optional[dict]:
    """Get norm by id or by year + month."""
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM norms WHERE id = $1", id)
        elif year is not None and month is not None:
            row = await conn.fetchrow("SELECT * FROM norms WHERE year = $1 AND month = $2", year, month)
        else:
            return None
        return dict(row) if row else None


async def norm_list(year: Optional[int] = None) -> list[dict]:
    """List norms, optionally filtered by year."""
    async with get_db() as conn:
        if year is not None:
            rows = await conn.fetch("SELECT * FROM norms WHERE year = $1 ORDER BY month", year)
        else:
            rows = await conn.fetch("SELECT * FROM norms ORDER BY year DESC, month")
        return [dict(row) for row in rows]


async def norm_delete(id: int) -> bool:
    """Delete norm by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM norms WHERE id = $1", id)
        return result.split()[-1] != '0'


# =============================================================================
# Exclusions CRUD
# =============================================================================

async def exclusion_add(pattern: str) -> dict:
    """Add exclusion pattern."""
    async with get_db() as conn:
        try:
            row = await conn.fetchrow(
                "INSERT INTO exclusions (pattern) VALUES ($1) RETURNING id",
                pattern
            )
            return {"id": row["id"], "pattern": pattern, "created": True}
        except Exception:
            # Already exists
            row = await conn.fetchrow("SELECT id FROM exclusions WHERE pattern = $1", pattern)
            return {"id": row["id"], "pattern": pattern, "created": False}


async def exclusion_list() -> list[dict]:
    """List all exclusion patterns."""
    async with get_db() as conn:
        rows = await conn.fetch("SELECT * FROM exclusions ORDER BY pattern")
        return [dict(row) for row in rows]


async def exclusion_delete(id: int) -> bool:
    """Delete exclusion by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM exclusions WHERE id = $1", id)
        return result.split()[-1] != '0'


async def is_excluded(event_summary: str) -> bool:
    """Check if event summary matches any exclusion pattern (case-insensitive)."""
    async with get_db() as conn:
        rows = await conn.fetch("SELECT pattern FROM exclusions")
        patterns = [row["pattern"].lower() for row in rows]
        return event_summary.strip().lower() in patterns


# =============================================================================
# Settings CRUD
# =============================================================================

async def config_get(key: str) -> Optional[str]:
    """Get setting value by key."""
    async with get_db() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row["value"] if row else None


async def config_set(key: str, value: str) -> dict:
    """Set setting value."""
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """,
            key, value
        )
        return {"key": key, "value": value}


async def config_list() -> dict[str, str]:
    """Get all settings as dictionary."""
    async with get_db() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}


# =============================================================================
# Utility functions for parser
# =============================================================================

async def get_project_by_code(code: str) -> Optional[dict]:
    """Get project by code (for parser)."""
    return await project_get(code=code)


async def get_projects_by_code(code: str) -> list[dict]:
    """Get ALL active projects with the same code, ordered by structure_level DESC."""
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM projects WHERE code = $1 AND is_active = TRUE ORDER BY structure_level DESC",
            code.upper()
        )
        return [dict(row) for row in rows]


async def get_phase_by_code(project_code: str, phase_code: str) -> Optional[dict]:
    """Get phase by project code and phase code."""
    project = await project_get(code=project_code)
    if not project:
        return None
    return await phase_get(project_id=project["id"], code=phase_code)


async def get_task_by_code(project_code: str, task_code: str) -> Optional[dict]:
    """Get task by project code and task code."""
    project = await project_get(code=project_code)
    if not project:
        return None
    return await task_get(project_id=project["id"], code=task_code)


# Aliases
get_project = get_project_by_code
get_phase = get_phase_by_code
get_task = get_task_by_code
get_setting = config_get


async def get_norm(year: int, month: int) -> Optional[dict]:
    """Get norm by year and month."""
    return await norm_get(year=year, month=month)
