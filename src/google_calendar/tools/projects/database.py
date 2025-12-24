"""
Database management for projects and organizations using PostgreSQL.

Uses shared connection pool from google_calendar.db.connection.
Schema managed via google_calendar/db/schema.sql.

Schema version 2:
- Organizations table with M:N relationship to projects
- Tasks linked to phases (not projects) for proper hierarchy: PROJECT -> PHASE -> TASK
- Extended project fields (full_name, country, sector, dates, contract info)
"""

from typing import Optional

from google_calendar.db.connection import get_db, check_db_exists


SCHEMA_VERSION = 2

# Organization types for organizations table
ORGANIZATION_TYPES = (
    'donor', 'dfi', 'government', 'bank', 'mfi', 'nbfi',
    'consulting', 'ngo', 'other'
)

# Roles for project-organization relationships
ORG_ROLES = (
    'donor', 'client', 'implementing_agency',
    'partner', 'subcontractor', 'beneficiary'
)

# Relationship statuses for organizations
RELATIONSHIP_STATUSES = ('prospect', 'active', 'dormant', 'former')


async def database_exists() -> bool:
    """Check if database tables exist."""
    return await check_db_exists()


async def ensure_database() -> bool:
    """Ensure database exists. Schema is managed via schema.sql."""
    return await database_exists()


# =============================================================================
# Projects CRUD
# =============================================================================

async def project_add(
    code: str,
    description: str,
    is_billable: bool = False,
    is_active: bool = True,
    structure_level: int = 1,
    full_name: Optional[str] = None,
    country: Optional[str] = None,
    sector: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    contract_value: Optional[float] = None,
    currency: str = 'EUR',
    context: Optional[str] = None,
) -> dict:
    """Create a new project with v2 business fields. Returns created project with id."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (code, description, is_billable, is_active, structure_level,
                                 full_name, country, sector, start_date, end_date, contract_value, currency, context)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
            """,
            code.upper(), description, is_billable, is_active, structure_level,
            full_name, country, sector, start_date, end_date, contract_value, currency, context
        )
        return await project_get(id=row['id'])


async def project_get(id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get project by id or code."""
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", id)
        elif code is not None:
            row = await conn.fetchrow("SELECT * FROM projects WHERE code = $1", code.upper())
        else:
            return None
        return dict(row) if row else None


async def project_list(billable_only: bool = False, active_only: bool = False) -> list[dict]:
    """List all projects with owner's role (contact_id=1).

    Each project includes:
        - my_role: role_code if owner is assigned to project (e.g. 'TL', 'KE')
        - my_role_name: role name in English (e.g. 'Team Leader', 'Key Expert')
    """
    async with get_db() as conn:
        conditions = []
        params = []
        param_idx = 1

        if billable_only:
            conditions.append(f"p.is_billable = ${param_idx}")
            params.append(True)
            param_idx += 1
        if active_only:
            conditions.append(f"p.is_active = ${param_idx}")
            params.append(True)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        # Join with contact_projects to get owner's role (contact_id=1)
        query = f"""
            SELECT p.*,
                   cp.role_code as my_role,
                   pr.role_name_en as my_role_name
            FROM projects p
            LEFT JOIN contact_projects cp ON cp.project_id = p.id AND cp.contact_id = 1 AND cp.is_active = TRUE
            LEFT JOIN project_roles pr ON pr.role_code = cp.role_code
            {where_clause}
            ORDER BY p.code
        """

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def project_update(id: int, **kwargs) -> Optional[dict]:
    """Update project by id. Supports v2 fields."""
    allowed_fields = {"code", "description", "is_billable", "is_active", "structure_level",
                     "full_name", "country", "sector", "start_date", "end_date", "contract_value", "currency", "context"}
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
    set_clause = ", ".join(set_parts)

    async with get_db() as conn:
        result = await conn.execute(
            f"UPDATE projects SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(values)}",
            *values
        )
        if result == "UPDATE 0":
            return None
        return await project_get(id=id)


async def project_delete(id: int) -> bool:
    """Delete project by id (cascades to phases/tasks)."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM projects WHERE id = $1", id)
        return result != "DELETE 0"


async def project_list_active() -> list[dict]:
    """Get active projects with their phases and tasks.

    Returns projects with:
        - phases: list of phases, each with nested 'tasks' for phase-linked tasks
        - universal_tasks: tasks linked directly to project (phase_id=null)
        - format: event summary format based on structure_level

    Task organization:
        - Phase-linked tasks appear under their respective phase['tasks']
        - Universal tasks (project_id set, phase_id null) appear in project['universal_tasks']
    """
    projects = await project_list(active_only=True)
    for project in projects:
        # Get phases with their tasks
        phases = await phase_list(project_id=project["id"])
        for phase in phases:
            phase_tasks = await task_list(phase_id=phase["id"])
            phase["tasks"] = phase_tasks
        project["phases"] = phases

        # Get universal tasks (linked to project, not to phase)
        all_tasks = await task_list(project_id=project["id"], include_universal=True)
        project["universal_tasks"] = [t for t in all_tasks if t.get("phase_id") is None]

        # Format hint for calendar events
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
            "id": row['id'],
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
    set_clause = ", ".join(set_parts)

    async with get_db() as conn:
        result = await conn.execute(f"UPDATE phases SET {set_clause} WHERE id = ${len(values)}", *values)
        if result == "UPDATE 0":
            return None
        return await phase_get(id=id)


async def phase_delete(id: int) -> bool:
    """Delete phase by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM phases WHERE id = $1", id)
        return result != "DELETE 0"


# =============================================================================
# Tasks CRUD
# =============================================================================

async def task_add(
    code: str,
    description: Optional[str] = None,
    phase_id: Optional[int] = None,
    project_id: Optional[int] = None
) -> dict:
    """Create a new task.

    Two modes:
        - phase_id set → task linked to specific phase
        - project_id set, phase_id null → universal task for all phases of project

    Args:
        code: Task code (will be uppercased)
        description: Task description
        phase_id: Link to specific phase (mutually exclusive with project_id)
        project_id: Link to project for universal task (mutually exclusive with phase_id)

    Returns:
        Created task dict

    Raises:
        ValueError: If neither or both phase_id and project_id are provided
    """
    if (phase_id is None) == (project_id is None):
        raise ValueError("Exactly one of phase_id or project_id must be provided")

    async with get_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO tasks (phase_id, project_id, code, description) VALUES ($1, $2, $3, $4) RETURNING id",
            phase_id, project_id, code.upper(), description
        )
        return await task_get(id=row['id'])


async def task_get(
    id: Optional[int] = None,
    phase_id: Optional[int] = None,
    project_id: Optional[int] = None,
    code: Optional[str] = None
) -> Optional[dict]:
    """Get task by id, by phase_id + code, or by project_id + code.

    Args:
        id: Task ID (takes precedence)
        phase_id: Phase ID (used with code for phase-linked tasks)
        project_id: Project ID (used with code for universal tasks)
        code: Task code

    Returns:
        Task dict or None if not found
    """
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", id)
        elif phase_id is not None and code is not None:
            row = await conn.fetchrow(
                "SELECT * FROM tasks WHERE phase_id = $1 AND code = $2",
                phase_id, code.upper()
            )
        elif project_id is not None and code is not None:
            row = await conn.fetchrow(
                "SELECT * FROM tasks WHERE project_id = $1 AND phase_id IS NULL AND code = $2",
                project_id, code.upper()
            )
        else:
            return None
        return dict(row) if row else None


async def task_list(
    phase_id: Optional[int] = None,
    project_id: Optional[int] = None,
    include_universal: bool = True
) -> list[dict]:
    """List tasks, optionally filtered by phase or project.

    Args:
        phase_id: Filter by specific phase
        project_id: Filter by project (includes phase-linked and universal tasks)
        include_universal: When filtering by project, include universal tasks (default True)

    Returns:
        List of task dicts. For project filter, returns both:
        - Phase-linked tasks (via phases table)
        - Universal project tasks (project_id set, phase_id null)
    """
    async with get_db() as conn:
        if phase_id is not None:
            rows = await conn.fetch(
                "SELECT * FROM tasks WHERE phase_id = $1 ORDER BY code",
                phase_id
            )
        elif project_id is not None:
            if include_universal:
                # Both phase-linked and universal tasks
                rows = await conn.fetch(
                    """
                    SELECT t.*, p.code as phase_code FROM tasks t
                    LEFT JOIN phases p ON t.phase_id = p.id
                    WHERE p.project_id = $1 OR (t.project_id = $1 AND t.phase_id IS NULL)
                    ORDER BY COALESCE(p.code, ''), t.code
                    """,
                    project_id
                )
            else:
                # Only phase-linked tasks
                rows = await conn.fetch(
                    """
                    SELECT t.*, p.code as phase_code FROM tasks t
                    JOIN phases p ON t.phase_id = p.id
                    WHERE p.project_id = $1
                    ORDER BY p.code, t.code
                    """,
                    project_id
                )
        else:
            rows = await conn.fetch("SELECT * FROM tasks ORDER BY COALESCE(phase_id, 0), code")
        return [dict(row) for row in rows]


async def task_update(id: int, **kwargs) -> Optional[dict]:
    """Update task by id.

    Can change task binding:
        - Set phase_id (and project_id=None) → link to specific phase
        - Set project_id (and phase_id=None) → make universal for project

    Args:
        id: Task ID
        **kwargs: Fields to update (code, description, phase_id, project_id)

    Returns:
        Updated task dict or None if not found
    """
    allowed_fields = {"code", "description", "phase_id", "project_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

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
    set_clause = ", ".join(set_parts)

    async with get_db() as conn:
        result = await conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ${len(values)}", *values)
        if result == "UPDATE 0":
            return None
        return await task_get(id=id)


async def task_delete(id: int) -> bool:
    """Delete task by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM tasks WHERE id = $1", id)
        return result != "DELETE 0"


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
        return {"id": row['id'], "year": year, "month": month, "hours": hours}


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
        return result != "DELETE 0"


# =============================================================================
# Exclusions CRUD
# =============================================================================

async def exclusion_add(pattern: str) -> dict:
    """Add exclusion pattern."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO exclusions (pattern) VALUES ($1)
            ON CONFLICT (pattern) DO NOTHING
            RETURNING id
            """,
            pattern
        )
        if row:
            return {"id": row['id'], "pattern": pattern, "created": True}
        row = await conn.fetchrow("SELECT id FROM exclusions WHERE pattern = $1", pattern)
        return {"id": row['id'], "pattern": pattern, "created": False}


async def exclusion_list() -> list[dict]:
    """List all exclusion patterns."""
    async with get_db() as conn:
        rows = await conn.fetch("SELECT * FROM exclusions ORDER BY pattern")
        return [dict(row) for row in rows]


async def exclusion_delete(id: int) -> bool:
    """Delete exclusion by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM exclusions WHERE id = $1", id)
        return result != "DELETE 0"


async def is_excluded(event_summary: str) -> bool:
    """Check if event summary matches any exclusion pattern (case-insensitive)."""
    async with get_db() as conn:
        rows = await conn.fetch("SELECT pattern FROM exclusions")
        patterns = [row['pattern'].lower() for row in rows]
        return event_summary.strip().lower() in patterns


# =============================================================================
# Settings CRUD
# =============================================================================

async def config_get(key: str) -> Optional[str]:
    """Get setting value by key."""
    async with get_db() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row['value'] if row else None


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
        return {row['key']: row['value'] for row in rows}


# =============================================================================
# Utility functions for parser (lookup by code)
# =============================================================================

async def get_project_by_code(code: str) -> Optional[dict]:
    """Get project by code (for parser). Returns first match."""
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
    """Get phase by project code and phase code (for parser)."""
    project = await project_get(code=project_code)
    if not project:
        return None
    return await phase_get(project_id=project["id"], code=phase_code)


async def get_task_by_code(project_code: str, task_code: str) -> Optional[dict]:
    """Get task by project code and task code (for parser).

    v2 note: Tasks are now linked to phases, not projects.
    This function searches all phases of the project for the task.
    """
    project = await project_get(code=project_code)
    if not project:
        return None
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT t.* FROM tasks t
            JOIN phases p ON t.phase_id = p.id
            WHERE p.project_id = $1 AND t.code = $2
            LIMIT 1
            """,
            project["id"], task_code.upper()
        )
        return dict(row) if row else None


async def get_task_by_project_code(project_code: str, task_code: str) -> Optional[dict]:
    """Alias for get_task_by_code for backward compatibility."""
    return await get_task_by_code(project_code, task_code)


# Aliases for backward compatibility with parser
get_project = get_project_by_code
get_phase = get_phase_by_code
get_task = get_task_by_code
get_setting = config_get


async def get_norm(year: int, month: int) -> Optional[dict]:
    """Get norm by year and month."""
    return await norm_get(year=year, month=month)


# =============================================================================
# Organizations CRUD (v2)
# =============================================================================

async def org_add(
    name: str,
    short_name: Optional[str] = None,
    name_local: Optional[str] = None,
    organization_type: Optional[str] = None,
    parent_org_id: Optional[int] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
    website: Optional[str] = None,
    context: Optional[str] = None,
    relationship_status: str = 'active',
    first_contact_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Create a new organization."""
    if organization_type and organization_type not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if relationship_status not in RELATIONSHIP_STATUSES:
        raise ValueError(f"Invalid relationship_status. Must be one of: {RELATIONSHIP_STATUSES}")

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO organizations (name, short_name, name_local, organization_type, parent_org_id,
                                      country, city, website, context, relationship_status, first_contact_date, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            name, short_name, name_local, organization_type, parent_org_id,
            country, city, website, context, relationship_status, first_contact_date, notes
        )
        return await org_get(id=row['id'])


async def org_get(id: Optional[int] = None, name: Optional[str] = None) -> Optional[dict]:
    """Get organization by id or name."""
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM organizations WHERE id = $1", id)
        elif name is not None:
            row = await conn.fetchrow("SELECT * FROM organizations WHERE name = $1", name)
        else:
            return None
        return dict(row) if row else None


async def org_list(
    organization_type: Optional[str] = None,
    country: Optional[str] = None,
    relationship_status: Optional[str] = None,
    active_only: bool = True,
) -> list[dict]:
    """List organizations with optional filters."""
    async with get_db() as conn:
        conditions = []
        params = []
        param_idx = 1

        if organization_type:
            conditions.append(f"organization_type = ${param_idx}")
            params.append(organization_type)
            param_idx += 1
        if country:
            conditions.append(f"country = ${param_idx}")
            params.append(country)
            param_idx += 1
        if relationship_status:
            conditions.append(f"relationship_status = ${param_idx}")
            params.append(relationship_status)
            param_idx += 1
        if active_only:
            conditions.append("is_active = TRUE")

        query = "SELECT * FROM organizations"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY name"

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def org_update(id: int, **kwargs) -> Optional[dict]:
    """Update organization by id."""
    allowed_fields = {"name", "short_name", "name_local", "organization_type", "parent_org_id",
                     "country", "city", "website", "context", "relationship_status",
                     "first_contact_date", "is_active", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await org_get(id=id)

    if "organization_type" in updates and updates["organization_type"] not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if "relationship_status" in updates and updates["relationship_status"] not in RELATIONSHIP_STATUSES:
        raise ValueError(f"Invalid relationship_status. Must be one of: {RELATIONSHIP_STATUSES}")

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)

    values.append(id)
    set_clause = ", ".join(set_parts)

    async with get_db() as conn:
        result = await conn.execute(
            f"UPDATE organizations SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(values)}",
            *values
        )
        if result == "UPDATE 0":
            return None
    return await org_get(id=id)


async def org_delete(id: int) -> bool:
    """Delete organization by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM organizations WHERE id = $1", id)
        return result != "DELETE 0"


async def org_search(query: str, limit: int = 20) -> list[dict]:
    """Search organizations by name or short_name."""
    async with get_db() as conn:
        search_pattern = f"%{query}%"
        rows = await conn.fetch(
            """
            SELECT * FROM organizations
            WHERE name ILIKE $1
               OR short_name ILIKE $1
               OR name_local ILIKE $1
            ORDER BY name
            LIMIT $2
            """,
            search_pattern, limit
        )
        return [dict(row) for row in rows]


# =============================================================================
# Project-Organization Links CRUD (v2)
# =============================================================================

async def project_org_add(
    project_id: int,
    organization_id: int,
    org_role: str,
    contract_value: Optional[float] = None,
    currency: str = 'EUR',
    is_lead: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Link an organization to a project with a specific role."""
    if org_role not in ORG_ROLES:
        raise ValueError(f"Invalid org_role. Must be one of: {ORG_ROLES}")

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO project_organizations (project_id, organization_id, org_role,
                                              contract_value, currency, is_lead, start_date, end_date, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            project_id, organization_id, org_role, contract_value, currency, is_lead, start_date, end_date, notes
        )
        return await project_org_get(id=row['id'])


async def project_org_get(id: int) -> Optional[dict]:
    """Get project-organization link by id."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT po.*, p.code as project_code, o.name as organization_name
            FROM project_organizations po
            JOIN projects p ON po.project_id = p.id
            JOIN organizations o ON po.organization_id = o.id
            WHERE po.id = $1
            """,
            id
        )
        return dict(row) if row else None


async def project_org_list(
    project_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    org_role: Optional[str] = None,
) -> list[dict]:
    """List project-organization links with optional filters."""
    async with get_db() as conn:
        conditions = []
        params = []
        param_idx = 1

        if project_id:
            conditions.append(f"po.project_id = ${param_idx}")
            params.append(project_id)
            param_idx += 1
        if organization_id:
            conditions.append(f"po.organization_id = ${param_idx}")
            params.append(organization_id)
            param_idx += 1
        if org_role:
            conditions.append(f"po.org_role = ${param_idx}")
            params.append(org_role)
            param_idx += 1

        query = """
            SELECT po.*, p.code as project_code, o.name as organization_name
            FROM project_organizations po
            JOIN projects p ON po.project_id = p.id
            JOIN organizations o ON po.organization_id = o.id
        """
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY po.project_id, po.is_lead DESC, o.name"

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def project_org_update(id: int, **kwargs) -> Optional[dict]:
    """Update project-organization link by id."""
    allowed_fields = {"org_role", "contract_value", "currency", "is_lead", "start_date", "end_date", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await project_org_get(id=id)

    if "org_role" in updates and updates["org_role"] not in ORG_ROLES:
        raise ValueError(f"Invalid org_role. Must be one of: {ORG_ROLES}")

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)

    values.append(id)
    set_clause = ", ".join(set_parts)

    async with get_db() as conn:
        result = await conn.execute(f"UPDATE project_organizations SET {set_clause} WHERE id = ${len(values)}", *values)
        if result == "UPDATE 0":
            return None
    return await project_org_get(id=id)


async def project_org_delete(id: int) -> bool:
    """Delete project-organization link by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM project_organizations WHERE id = $1", id)
        return result != "DELETE 0"


async def get_project_organizations(project_id: int) -> list[dict]:
    """Get all organizations linked to a project."""
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT o.*, po.org_role, po.is_lead, po.contract_value as link_contract_value,
                   po.currency as link_currency, po.start_date as link_start_date,
                   po.end_date as link_end_date, po.notes as link_notes
            FROM organizations o
            JOIN project_organizations po ON o.id = po.organization_id
            WHERE po.project_id = $1
            ORDER BY po.is_lead DESC, o.name
            """,
            project_id
        )
        return [dict(row) for row in rows]


async def get_organization_projects(organization_id: int) -> list[dict]:
    """Get all projects linked to an organization."""
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT p.*, po.org_role, po.is_lead, po.contract_value as link_contract_value,
                   po.currency as link_currency, po.start_date as link_start_date,
                   po.end_date as link_end_date, po.notes as link_notes
            FROM projects p
            JOIN project_organizations po ON p.id = po.project_id
            WHERE po.organization_id = $1
            ORDER BY p.is_active DESC, p.code
            """,
            organization_id
        )
        return [dict(row) for row in rows]


# =============================================================================
# Sync wrappers for backward compatibility (used by manage.py OPERATIONS dict)
# =============================================================================
# Note: These are needed because manage.py uses lambda functions that expect sync results.
# The actual execution happens in the async tool function.

def init_database():
    """Placeholder - schema is managed via schema.sql applied by workflow."""
    pass


def get_database_path():
    """Placeholder for compatibility - not used with PostgreSQL."""
    return None
