"""
Database management for projects and organizations.

SQLite database schema and operations for projects, phases, tasks, organizations, norms, and settings.
All entities have integer id as primary key for batch operations.
Database location: ~/.mcp/google-calendar/time_tracking.db

Schema version 2:
- Organizations table with M:N relationship to projects
- Tasks linked to phases (not projects) for proper hierarchy: PROJECT → PHASE → TASK
- Extended project fields (full_name, country, sector, dates, contract info)
"""

import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from google_calendar.utils.config import get_app_dir


DATABASE_NAME = "time_tracking.db"
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
    """Initialize database with schema v2.

    Creates tables:
    - schema_version: tracks schema version for migrations
    - organizations: organization registry with types and relationships
    - projects: extended with business fields (full_name, country, sector, dates)
    - project_organizations: M:N relationship between projects and organizations
    - phases: project phases
    - tasks: linked to phases (not projects) for proper hierarchy
    - norms, exclusions, settings: time tracking config

    All entities have integer id as primary key for batch operations.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Schema version tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

        # Organizations table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                short_name TEXT,
                name_local TEXT,
                organization_type TEXT CHECK(organization_type IN {ORGANIZATION_TYPES}),
                parent_org_id INTEGER REFERENCES organizations(id),
                country TEXT,
                city TEXT,
                website TEXT,
                context TEXT,
                relationship_status TEXT CHECK(relationship_status IN {RELATIONSHIP_STATUSES}),
                first_contact_date DATE,
                is_active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Projects table - extended with business fields
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                full_name TEXT,
                description TEXT NOT NULL,
                country TEXT,
                sector TEXT,
                is_billable INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                position TEXT,
                structure_level INTEGER NOT NULL DEFAULT 1,
                start_date DATE,
                end_date DATE,
                contract_value REAL,
                currency TEXT DEFAULT 'EUR',
                context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Project-Organization M:N relationship
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS project_organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                org_role TEXT NOT NULL CHECK(org_role IN {ORG_ROLES}),
                contract_value REAL,
                currency TEXT DEFAULT 'EUR',
                is_lead INTEGER NOT NULL DEFAULT 0,
                start_date DATE,
                end_date DATE,
                notes TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (organization_id) REFERENCES organizations(id),
                UNIQUE(project_id, organization_id, org_role)
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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, code)
            )
        """)

        # Tasks table - references PHASE (not project!) for proper hierarchy
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (phase_id) REFERENCES phases(id) ON DELETE CASCADE,
                UNIQUE(phase_id, code)
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_organizations_type ON organizations(organization_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_organizations_country ON organizations(country)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_code ON projects(code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_country ON projects(country)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_project_orgs_project ON project_organizations(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_project_orgs_org ON project_organizations(organization_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_phases_project ON phases(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_norms_year_month ON norms(year, month)")

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


def _get_schema_version() -> int:
    """Get current schema version from database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        if not cursor.fetchone():
            return 1  # No version table = v1
        cursor.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row and row[0] else 1


def _migrate_v1_to_v2() -> None:
    """Migrate from schema v1 to v2.

    Changes:
    1. Add schema_version table
    2. Create organizations table
    3. Create project_organizations table
    4. Add new columns to projects (full_name, country, sector, dates, contract, context)
    5. Add updated_at to phases
    6. Migrate tasks from project_id to phase_id (CRITICAL)
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Schema version tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Organizations table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                short_name TEXT,
                name_local TEXT,
                organization_type TEXT CHECK(organization_type IN {ORGANIZATION_TYPES}),
                parent_org_id INTEGER REFERENCES organizations(id),
                country TEXT,
                city TEXT,
                website TEXT,
                context TEXT,
                relationship_status TEXT CHECK(relationship_status IN {RELATIONSHIP_STATUSES}),
                first_contact_date DATE,
                is_active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Project-Organization M:N relationship
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS project_organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                org_role TEXT NOT NULL CHECK(org_role IN {ORG_ROLES}),
                contract_value REAL,
                currency TEXT DEFAULT 'EUR',
                is_lead INTEGER NOT NULL DEFAULT 0,
                start_date DATE,
                end_date DATE,
                notes TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (organization_id) REFERENCES organizations(id),
                UNIQUE(project_id, organization_id, org_role)
            )
        """)

        # 4. Add new columns to projects
        cursor.execute("PRAGMA table_info(projects)")
        columns = [col[1] for col in cursor.fetchall()]

        if "is_active" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "full_name" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN full_name TEXT")
        if "country" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN country TEXT")
        if "sector" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN sector TEXT")
        if "start_date" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN start_date DATE")
        if "end_date" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN end_date DATE")
        if "contract_value" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN contract_value REAL")
        if "currency" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN currency TEXT DEFAULT 'EUR'")
        if "context" not in columns:
            cursor.execute("ALTER TABLE projects ADD COLUMN context TEXT")

        # 5. Add updated_at to phases if missing
        cursor.execute("PRAGMA table_info(phases)")
        phase_columns = [col[1] for col in cursor.fetchall()]
        if "updated_at" not in phase_columns:
            cursor.execute("ALTER TABLE phases ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        # 6. Migrate tasks from project_id to phase_id (CRITICAL FIX)
        cursor.execute("PRAGMA table_info(tasks)")
        task_columns = [col[1] for col in cursor.fetchall()]

        if "project_id" in task_columns and "phase_id" not in task_columns:
            # Need to migrate tasks structure

            # Step 1: Ensure every project with tasks has at least one phase
            cursor.execute("""
                INSERT INTO phases (project_id, code, description)
                SELECT DISTINCT t.project_id, 'DEFAULT', 'Default phase (migrated from v1)'
                FROM tasks t
                WHERE NOT EXISTS (
                    SELECT 1 FROM phases p WHERE p.project_id = t.project_id
                )
            """)

            # Step 2: Create new tasks table with phase_id
            cursor.execute("""
                CREATE TABLE tasks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phase_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (phase_id) REFERENCES phases(id) ON DELETE CASCADE,
                    UNIQUE(phase_id, code)
                )
            """)

            # Step 3: Migrate tasks to first phase of their project
            cursor.execute("""
                INSERT INTO tasks_new (id, phase_id, code, description, created_at)
                SELECT
                    t.id,
                    (SELECT p.id FROM phases p WHERE p.project_id = t.project_id ORDER BY p.id LIMIT 1),
                    t.code,
                    t.description,
                    t.created_at
                FROM tasks t
                WHERE EXISTS (SELECT 1 FROM phases p WHERE p.project_id = t.project_id)
            """)

            # Step 4: Replace tables
            cursor.execute("DROP TABLE tasks")
            cursor.execute("ALTER TABLE tasks_new RENAME TO tasks")

            # Step 5: Recreate index
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase_id)")

        # Create new indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_organizations_type ON organizations(organization_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_organizations_country ON organizations(country)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_country ON projects(country)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_project_orgs_project ON project_organizations(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_project_orgs_org ON project_organizations(organization_id)")

        # Update schema version
        cursor.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))


def ensure_database() -> bool:
    """Ensure database exists and is initialized. Returns True if newly created.

    Handles schema migrations:
    - v1 → v2: organizations, project-org links, tasks to phase_id
    """
    newly_created = not database_exists()
    if newly_created:
        init_database()
    else:
        # Check and run migrations
        current_version = _get_schema_version()
        if current_version < 2:
            _migrate_v1_to_v2()
    return newly_created


# =============================================================================
# Projects CRUD
# =============================================================================

def project_add(
    code: str,
    description: str,
    is_billable: bool = False,
    is_active: bool = True,
    position: Optional[str] = None,
    structure_level: int = 1,
    # New v2 fields
    full_name: Optional[str] = None,
    country: Optional[str] = None,
    sector: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    contract_value: Optional[float] = None,
    currency: str = 'EUR',
    context: Optional[str] = None,
) -> dict:
    """Create a new project with business context.

    Args:
        code: Short project code (e.g., 'PROJ01')
        description: Brief description
        is_billable: Whether project is billable
        is_active: Whether project is active
        position: User's role/position on project
        structure_level: 1=project only, 2=project+phases, 3=project+phases+tasks
        full_name: Full project name
        country: Project country
        sector: Industry sector
        start_date: Project start date (YYYY-MM-DD)
        end_date: Project end date (YYYY-MM-DD)
        contract_value: Total contract value
        currency: Currency code (default EUR)
        context: Additional context/notes

    Returns:
        Created project dict with id
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects (
                code, description, is_billable, is_active, position, structure_level,
                full_name, country, sector, start_date, end_date, contract_value, currency, context
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code.upper(), description, int(is_billable), int(is_active), position, structure_level,
             full_name, country, sector, start_date, end_date, contract_value, currency, context)
        )
        return {
            "id": cursor.lastrowid,
            "code": code.upper(),
            "description": description,
            "is_billable": is_billable,
            "is_active": is_active,
            "position": position,
            "structure_level": structure_level,
            "full_name": full_name,
            "country": country,
            "sector": sector,
            "start_date": start_date,
            "end_date": end_date,
            "contract_value": contract_value,
            "currency": currency,
            "context": context,
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
            result["is_active"] = bool(result.get("is_active", 1))
            return result
        return None


def project_list(billable_only: bool = False, active_only: bool = False) -> list[dict]:
    """List all projects."""
    with get_connection() as conn:
        cursor = conn.cursor()
        conditions = []
        if billable_only:
            conditions.append("is_billable = 1")
        if active_only:
            conditions.append("is_active = 1")

        query = "SELECT * FROM projects"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY code"

        cursor.execute(query)
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_billable"] = bool(item["is_billable"])
            item["is_active"] = bool(item.get("is_active", 1))
            results.append(item)
        return results


def project_update(id: int, **kwargs) -> Optional[dict]:
    """Update project by id.

    Allowed fields: code, description, is_billable, is_active, position, structure_level,
    full_name, country, sector, start_date, end_date, contract_value, currency, context
    """
    allowed_fields = {
        "code", "description", "is_billable", "is_active", "position", "structure_level",
        "full_name", "country", "sector", "start_date", "end_date", "contract_value", "currency", "context"
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return project_get(id=id)

    if "is_billable" in updates:
        updates["is_billable"] = int(updates["is_billable"])
    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])
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


def project_list_active() -> list[dict]:
    """Get active projects with their phases and tasks.

    Returns projects with complete structure for event creation.
    Use this when creating time tracking events to know available projects.
    """
    projects = project_list(active_only=True)
    for project in projects:
        project["phases"] = phase_list(project_id=project["id"])
        project["tasks"] = task_list(project_id=project["id"])
        # Add format hint based on structure_level
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
# Tasks CRUD (linked to phases, not projects)
# =============================================================================

def task_add(phase_id: int, code: str, description: Optional[str] = None) -> dict:
    """Create a new task for a phase.

    Tasks are linked to phases, not directly to projects.
    Hierarchy: PROJECT → PHASE → TASK

    Args:
        phase_id: ID of the parent phase
        code: Task code (will be uppercased)
        description: Optional description

    Returns:
        Created task dict with id
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (phase_id, code, description) VALUES (?, ?, ?)",
            (phase_id, code.upper(), description)
        )
        return {
            "id": cursor.lastrowid,
            "phase_id": phase_id,
            "code": code.upper(),
            "description": description
        }


def task_get(id: Optional[int] = None, phase_id: Optional[int] = None, code: Optional[str] = None) -> Optional[dict]:
    """Get task by id or by phase_id + code.

    Args:
        id: Task ID
        phase_id: Phase ID (requires code)
        code: Task code (requires phase_id)

    Returns:
        Task dict or None
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if id is not None:
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (id,))
        elif phase_id is not None and code is not None:
            cursor.execute(
                "SELECT * FROM tasks WHERE phase_id = ? AND code = ?",
                (phase_id, code.upper())
            )
        else:
            return None
        row = cursor.fetchone()
        return dict(row) if row else None


def task_list(phase_id: Optional[int] = None, project_id: Optional[int] = None) -> list[dict]:
    """List tasks, optionally filtered by phase or project.

    Args:
        phase_id: Filter by specific phase
        project_id: Filter by project (lists tasks from all phases of the project)

    Returns:
        List of task dicts
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if phase_id is not None:
            cursor.execute(
                "SELECT * FROM tasks WHERE phase_id = ? ORDER BY code",
                (phase_id,)
            )
        elif project_id is not None:
            # Get tasks from all phases of the project
            cursor.execute(
                """
                SELECT t.* FROM tasks t
                JOIN phases p ON t.phase_id = p.id
                WHERE p.project_id = ?
                ORDER BY p.code, t.code
                """,
                (project_id,)
            )
        else:
            cursor.execute("SELECT * FROM tasks ORDER BY phase_id, code")
        return [dict(row) for row in cursor.fetchall()]


def task_update(id: int, **kwargs) -> Optional[dict]:
    """Update task by id.

    Allowed fields: code, description, phase_id (to move task to another phase)
    """
    allowed_fields = {"code", "description", "phase_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return task_get(id=id)

    if "code" in updates:
        updates["code"] = updates["code"].upper()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tasks SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)
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
    """Get ALL active projects with the same code, ordered by structure_level DESC.

    This allows multiple projects with same code but different structure levels.
    Example: CAYIB Level 3 (with phases+tasks) and CAYIB Level 2 (phases only).
    Only returns active projects (is_active=1) for parser use.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM projects WHERE code = ? AND is_active = 1 ORDER BY structure_level DESC",
            (code.upper(),)
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_billable"] = bool(item["is_billable"])
            item["is_active"] = bool(item.get("is_active", 1))
            results.append(item)
        return results


def get_phase_by_code(project_code: str, phase_code: str) -> Optional[dict]:
    """Get phase by project code and phase code (for parser)."""
    project = project_get(code=project_code)
    if not project:
        return None
    return phase_get(project_id=project["id"], code=phase_code)


def get_task_by_code(project_code: str, phase_code: str, task_code: str) -> Optional[dict]:
    """Get task by project code, phase code, and task code (for parser).

    Args:
        project_code: Project code
        phase_code: Phase code
        task_code: Task code

    Returns:
        Task dict or None
    """
    phase = get_phase_by_code(project_code, phase_code)
    if not phase:
        return None
    return task_get(phase_id=phase["id"], code=task_code)


def get_task_by_project_code(project_code: str, task_code: str) -> Optional[dict]:
    """Get task by project code and task code (searches all phases).

    For backward compatibility - searches across all phases of the project.

    Args:
        project_code: Project code
        task_code: Task code

    Returns:
        First matching task dict or None
    """
    project = project_get(code=project_code)
    if not project:
        return None

    # Search tasks in all phases of the project
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.* FROM tasks t
            JOIN phases p ON t.phase_id = p.id
            WHERE p.project_id = ? AND t.code = ?
            LIMIT 1
            """,
            (project["id"], task_code.upper())
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# Aliases for backward compatibility with parser
get_project = get_project_by_code
get_phase = get_phase_by_code
get_task = get_task_by_project_code  # backward compat
get_setting = config_get
get_norm = lambda year, month: norm_get(year=year, month=month)


# =============================================================================
# Organizations CRUD
# =============================================================================

def org_add(
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
    """Create a new organization.

    Args:
        name: Unique organization name
        short_name: Short/abbreviated name
        name_local: Name in local language
        organization_type: One of: donor, dfi, government, bank, mfi, nbfi, consulting, ngo, other
        parent_org_id: Parent organization ID (for subsidiaries)
        country: Country
        city: City
        website: Website URL
        context: Additional context
        relationship_status: One of: prospect, active, dormant, former
        first_contact_date: Date of first contact (YYYY-MM-DD)
        notes: Notes

    Returns:
        Created organization dict with id
    """
    if organization_type and organization_type not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if relationship_status not in RELATIONSHIP_STATUSES:
        raise ValueError(f"Invalid relationship_status. Must be one of: {RELATIONSHIP_STATUSES}")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO organizations (
                name, short_name, name_local, organization_type, parent_org_id,
                country, city, website, context, relationship_status, first_contact_date, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, short_name, name_local, organization_type, parent_org_id,
             country, city, website, context, relationship_status, first_contact_date, notes)
        )
        new_id = cursor.lastrowid
    return org_get(id=new_id)


def org_get(id: Optional[int] = None, name: Optional[str] = None) -> Optional[dict]:
    """Get organization by id or name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if id is not None:
            cursor.execute("SELECT * FROM organizations WHERE id = ?", (id,))
        elif name is not None:
            cursor.execute("SELECT * FROM organizations WHERE name = ?", (name,))
        else:
            return None
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["is_active"] = bool(result.get("is_active", 1))
            return result
        return None


def org_list(
    organization_type: Optional[str] = None,
    country: Optional[str] = None,
    relationship_status: Optional[str] = None,
    active_only: bool = True,
) -> list[dict]:
    """List organizations with optional filters.

    Args:
        organization_type: Filter by type
        country: Filter by country
        relationship_status: Filter by relationship status
        active_only: Only return active organizations (default True)

    Returns:
        List of organization dicts
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if organization_type:
            conditions.append("organization_type = ?")
            params.append(organization_type)
        if country:
            conditions.append("country = ?")
            params.append(country)
        if relationship_status:
            conditions.append("relationship_status = ?")
            params.append(relationship_status)
        if active_only:
            conditions.append("is_active = 1")

        query = "SELECT * FROM organizations"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY name"

        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_active"] = bool(item.get("is_active", 1))
            results.append(item)
        return results


def org_update(id: int, **kwargs) -> Optional[dict]:
    """Update organization by id.

    Allowed fields: name, short_name, name_local, organization_type, parent_org_id,
    country, city, website, context, relationship_status, first_contact_date, is_active, notes
    """
    allowed_fields = {
        "name", "short_name", "name_local", "organization_type", "parent_org_id",
        "country", "city", "website", "context", "relationship_status",
        "first_contact_date", "is_active", "notes"
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return org_get(id=id)

    # Validate enums
    if "organization_type" in updates and updates["organization_type"] not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if "relationship_status" in updates and updates["relationship_status"] not in RELATIONSHIP_STATUSES:
        raise ValueError(f"Invalid relationship_status. Must be one of: {RELATIONSHIP_STATUSES}")

    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE organizations SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        if cursor.rowcount == 0:
            return None
        return org_get(id=id)


def org_delete(id: int) -> bool:
    """Delete organization by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM organizations WHERE id = ?", (id,))
        return cursor.rowcount > 0


def org_search(query: str, limit: int = 20) -> list[dict]:
    """Search organizations by name (case-insensitive).

    Args:
        query: Search string
        limit: Max results

    Returns:
        List of matching organizations
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        search_pattern = f"%{query}%"
        cursor.execute(
            """
            SELECT * FROM organizations
            WHERE (name LIKE ? COLLATE NOCASE
                   OR short_name LIKE ? COLLATE NOCASE
                   OR name_local LIKE ? COLLATE NOCASE)
              AND is_active = 1
            ORDER BY name
            LIMIT ?
            """,
            (search_pattern, search_pattern, search_pattern, limit)
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_active"] = bool(item.get("is_active", 1))
            results.append(item)
        return results


# =============================================================================
# Project-Organization Links CRUD
# =============================================================================

def project_org_add(
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
    """Link an organization to a project with a specific role.

    Args:
        project_id: Project ID
        organization_id: Organization ID
        org_role: One of: donor, client, implementing_agency, partner, subcontractor, beneficiary
        contract_value: Contract value for this org in the project
        currency: Currency code
        is_lead: Whether this is the lead org for this role
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        notes: Notes

    Returns:
        Created link dict with id
    """
    if org_role not in ORG_ROLES:
        raise ValueError(f"Invalid org_role. Must be one of: {ORG_ROLES}")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO project_organizations (
                project_id, organization_id, org_role, contract_value, currency,
                is_lead, start_date, end_date, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, organization_id, org_role, contract_value, currency,
             int(is_lead), start_date, end_date, notes)
        )
        return {
            "id": cursor.lastrowid,
            "project_id": project_id,
            "organization_id": organization_id,
            "org_role": org_role,
            "contract_value": contract_value,
            "currency": currency,
            "is_lead": is_lead,
            "start_date": start_date,
            "end_date": end_date,
            "notes": notes,
        }


def project_org_get(id: int) -> Optional[dict]:
    """Get project-organization link by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM project_organizations WHERE id = ?", (id,))
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["is_lead"] = bool(result.get("is_lead", 0))
            return result
        return None


def project_org_list(
    project_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    org_role: Optional[str] = None,
) -> list[dict]:
    """List project-organization links with optional filters.

    Args:
        project_id: Filter by project
        organization_id: Filter by organization
        org_role: Filter by role

    Returns:
        List of link dicts with organization details
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if project_id is not None:
            conditions.append("po.project_id = ?")
            params.append(project_id)
        if organization_id is not None:
            conditions.append("po.organization_id = ?")
            params.append(organization_id)
        if org_role:
            conditions.append("po.org_role = ?")
            params.append(org_role)

        query = """
            SELECT po.*, o.name as org_name, o.short_name as org_short_name,
                   o.organization_type, o.country as org_country
            FROM project_organizations po
            JOIN organizations o ON po.organization_id = o.id
        """
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY po.is_lead DESC, o.name"

        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_lead"] = bool(item.get("is_lead", 0))
            results.append(item)
        return results


def project_org_update(id: int, **kwargs) -> Optional[dict]:
    """Update project-organization link by id.

    Allowed fields: org_role, contract_value, currency, is_lead, start_date, end_date, notes
    """
    allowed_fields = {"org_role", "contract_value", "currency", "is_lead", "start_date", "end_date", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return project_org_get(id)

    if "org_role" in updates and updates["org_role"] not in ORG_ROLES:
        raise ValueError(f"Invalid org_role. Must be one of: {ORG_ROLES}")

    if "is_lead" in updates:
        updates["is_lead"] = int(updates["is_lead"])

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE project_organizations SET {set_clause} WHERE id = ?", values)
        if cursor.rowcount == 0:
            return None
        return project_org_get(id)


def project_org_delete(id: int) -> bool:
    """Delete project-organization link by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM project_organizations WHERE id = ?", (id,))
        return cursor.rowcount > 0


def get_project_organizations(project_id: int) -> list[dict]:
    """Get all organizations linked to a project with their roles.

    Convenience function returning organizations grouped by role.
    """
    return project_org_list(project_id=project_id)


def get_organization_projects(organization_id: int) -> list[dict]:
    """Get all projects an organization is linked to.

    Returns project info along with the organization's role.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT po.*, p.code as project_code, p.description as project_description,
                   p.full_name as project_full_name, p.is_active as project_is_active
            FROM project_organizations po
            JOIN projects p ON po.project_id = p.id
            WHERE po.organization_id = ?
            ORDER BY p.code
            """,
            (organization_id,)
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_lead"] = bool(item.get("is_lead", 0))
            item["project_is_active"] = bool(item.get("project_is_active", 1))
            results.append(item)
        return results
