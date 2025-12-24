"""
Async database operations for contacts (PostgreSQL).

Used in cloud mode with asyncpg connection pool.
Database: google_calendar_mcp (shared with time_tracking)
"""

from typing import Optional
from google_calendar.db.connection import get_db

# Valid values for CHECK constraints
ORGANIZATION_TYPES = ('donor', 'client', 'partner', 'bfc', 'government', 'bank', 'mfi', 'other')
PREFERRED_CHANNELS = ('email', 'telegram', 'teams', 'phone', 'whatsapp')
CHANNEL_TYPES = (
    'email', 'phone', 'telegram_id', 'telegram_username', 'telegram_chat_id',
    'teams_id', 'teams_chat_id', 'whatsapp', 'linkedin', 'skype', 'google_calendar'
)
ROLE_CATEGORIES = ('consultant', 'client', 'donor', 'partner')


# =============================================================================
# Database State
# =============================================================================

async def contacts_tables_exist() -> bool:
    """Check if contacts tables exist in database."""
    try:
        async with get_db() as conn:
            row = await conn.fetchrow("""
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = 'contacts'
                )
            """)
            return row[0] if row else False
    except Exception:
        return False


async def ensure_contacts_schema() -> bool:
    """Ensure contacts tables exist. Returns True if newly created."""
    from google_calendar.db.connection import ensure_db_initialized
    await ensure_db_initialized()
    return False


# =============================================================================
# CONTACTS CRUD
# =============================================================================

async def contact_add(
    first_name: str,
    last_name: str,
    organization: Optional[str] = None,
    organization_type: Optional[str] = None,
    job_title: Optional[str] = None,
    department: Optional[str] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
    timezone: Optional[str] = None,
    preferred_channel: str = 'email',
    preferred_language: str = 'en',
    notes: Optional[str] = None
) -> dict:
    """Create a new contact. Returns created contact with id."""
    if organization_type and organization_type not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if preferred_channel not in PREFERRED_CHANNELS:
        raise ValueError(f"Invalid preferred_channel. Must be one of: {PREFERRED_CHANNELS}")

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO contacts (
                first_name, last_name, organization, organization_type,
                job_title, department, country, city, timezone,
                preferred_channel, preferred_language, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            first_name, last_name, organization, organization_type,
            job_title, department, country, city, timezone,
            preferred_channel, preferred_language, notes
        )
        return await contact_get(id=row["id"])


async def contact_get(
    id: Optional[int] = None,
    email: Optional[str] = None,
    telegram: Optional[str] = None,
    phone: Optional[str] = None
) -> Optional[dict]:
    """Get contact by id or by channel value."""
    async with get_db() as conn:
        if id is not None:
            row = await conn.fetchrow("SELECT * FROM v_contacts_full WHERE id = $1", id)
        elif email is not None:
            row = await conn.fetchrow(
                """
                SELECT cf.* FROM v_contacts_full cf
                JOIN contact_channels cc ON cf.id = cc.contact_id
                WHERE cc.channel_type = 'email' AND cc.channel_value = $1
                """,
                email
            )
        elif telegram is not None:
            row = await conn.fetchrow(
                """
                SELECT cf.* FROM v_contacts_full cf
                JOIN contact_channels cc ON cf.id = cc.contact_id
                WHERE cc.channel_type IN ('telegram_id', 'telegram_username', 'telegram_chat_id')
                  AND cc.channel_value = $1
                """,
                telegram.lstrip('@')
            )
        elif phone is not None:
            row = await conn.fetchrow(
                """
                SELECT cf.* FROM v_contacts_full cf
                JOIN contact_channels cc ON cf.id = cc.contact_id
                WHERE cc.channel_type = 'phone' AND cc.channel_value = $1
                """,
                phone
            )
        else:
            return None

        return dict(row) if row else None


async def contact_list(
    organization: Optional[str] = None,
    organization_type: Optional[str] = None,
    country: Optional[str] = None,
    project_id: Optional[int] = None,
    role_code: Optional[str] = None,
    active_only: bool = True
) -> list[dict]:
    """List contacts with optional filters."""
    async with get_db() as conn:
        if project_id is not None:
            query = "SELECT * FROM v_project_team WHERE project_id = $1"
            params = [project_id]
            if role_code:
                query += " AND role_code = $2"
                params.append(role_code)
            rows = await conn.fetch(query, *params)
        else:
            base = "v_contacts_full" if active_only else "contacts"
            conditions = []
            params = []
            idx = 1

            if organization:
                conditions.append(f"organization ILIKE ${idx}")
                params.append(f"%{organization}%")
                idx += 1
            if organization_type:
                conditions.append(f"organization_type = ${idx}")
                params.append(organization_type)
                idx += 1
            if country:
                conditions.append(f"country = ${idx}")
                params.append(country)
                idx += 1

            query = f"SELECT * FROM {base}"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY display_name"

            rows = await conn.fetch(query, *params)

        return [dict(row) for row in rows]


async def contact_update(id: int, **kwargs) -> Optional[dict]:
    """Update contact by id."""
    allowed_fields = {
        'first_name', 'last_name', 'organization', 'organization_type',
        'job_title', 'department', 'country', 'city', 'timezone',
        'preferred_channel', 'preferred_language', 'notes', 'is_active'
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await contact_get(id=id)

    if 'organization_type' in updates and updates['organization_type'] not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if 'preferred_channel' in updates and updates['preferred_channel'] not in PREFERRED_CHANNELS:
        raise ValueError(f"Invalid preferred_channel. Must be one of: {PREFERRED_CHANNELS}")

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    values.append(id)

    async with get_db() as conn:
        result = await conn.execute(
            f"UPDATE contacts SET {', '.join(set_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(values)}",
            *values
        )
        if result.split()[-1] == '0':
            return None
        return await contact_get(id=id)


async def contact_delete(id: int) -> bool:
    """Delete contact by id (cascades to channels and project assignments)."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM contacts WHERE id = $1", id)
        return result.split()[-1] != '0'


async def contact_search(
    query: str,
    limit: int = 20,
    threshold: int = 60
) -> list[dict]:
    """Search contacts across multiple fields."""
    query = query.strip()
    if not query:
        return []

    query_clean = query.lstrip('@').lower()
    search_pattern = f"%{query_clean}%"

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT
                cf.*,
                STRING_AGG(DISTINCT p.code, ',') as projects
            FROM v_contacts_full cf
            LEFT JOIN contact_channels cc ON cf.id = cc.contact_id
            LEFT JOIN contact_projects cp ON cf.id = cp.contact_id AND cp.is_active = TRUE
            LEFT JOIN projects p ON cp.project_id = p.id AND p.is_active = TRUE
            WHERE cf.display_name ILIKE $1
               OR cf.first_name ILIKE $1
               OR cf.last_name ILIKE $1
               OR cf.organization ILIKE $1
               OR cf.country ILIKE $1
               OR cf.job_title ILIKE $1
               OR cc.channel_value ILIKE $1
               OR p.code ILIKE $1
               OR p.description ILIKE $1
            GROUP BY cf.id, cf.first_name, cf.last_name, cf.display_name, cf.organization,
                     cf.organization_type, cf.job_title, cf.department, cf.country, cf.city,
                     cf.timezone, cf.preferred_channel, cf.preferred_language,
                     cf.primary_email, cf.primary_phone, cf.telegram_chat_id,
                     cf.telegram_username, cf.teams_chat_id, cf.notes, cf.created_at, cf.updated_at
            ORDER BY cf.display_name
            LIMIT $2
            """,
            search_pattern, limit
        )
        results = []
        for row in rows:
            item = dict(row)
            item['match_score'] = 100
            item['matched_field'] = 'like'
            if item.get('projects'):
                item['projects'] = [p.strip() for p in item['projects'].split(',') if p.strip()]
            results.append(item)
        return results


# =============================================================================
# CHANNELS CRUD
# =============================================================================

async def channel_add(
    contact_id: int,
    channel_type: str,
    channel_value: str,
    channel_label: Optional[str] = None,
    is_primary: bool = False,
    notes: Optional[str] = None
) -> dict:
    """Add a channel to a contact."""
    if channel_type not in CHANNEL_TYPES:
        raise ValueError(f"Invalid channel_type. Must be one of: {CHANNEL_TYPES}")

    if channel_type == 'telegram_username':
        channel_value = channel_value.lstrip('@')

    async with get_db() as conn:
        if is_primary:
            await conn.execute(
                """
                UPDATE contact_channels
                SET is_primary = FALSE
                WHERE contact_id = $1 AND channel_type = $2
                """,
                contact_id, channel_type
            )

        row = await conn.fetchrow(
            """
            INSERT INTO contact_channels (contact_id, channel_type, channel_value, channel_label, is_primary, notes)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            contact_id, channel_type, channel_value, channel_label, is_primary, notes
        )
        return {
            "id": row["id"],
            "contact_id": contact_id,
            "channel_type": channel_type,
            "channel_value": channel_value,
            "channel_label": channel_label,
            "is_primary": is_primary,
            "notes": notes
        }


async def channel_list(contact_id: int) -> list[dict]:
    """List all channels for a contact."""
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM contact_channels WHERE contact_id = $1 ORDER BY channel_type, is_primary DESC",
            contact_id
        )
        return [dict(row) for row in rows]


async def channel_get(id: int) -> Optional[dict]:
    """Get channel by id."""
    async with get_db() as conn:
        row = await conn.fetchrow("SELECT * FROM contact_channels WHERE id = $1", id)
        return dict(row) if row else None


async def channel_update(id: int, **kwargs) -> Optional[dict]:
    """Update channel by id."""
    allowed_fields = {'channel_value', 'channel_label', 'is_primary', 'notes'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await channel_get(id)

    current = await channel_get(id)
    if not current:
        return None

    async with get_db() as conn:
        if updates.get('is_primary'):
            await conn.execute(
                """
                UPDATE contact_channels
                SET is_primary = FALSE
                WHERE contact_id = $1 AND channel_type = $2 AND id != $3
                """,
                current['contact_id'], current['channel_type'], id
            )

        set_parts = []
        values = []
        for i, (k, v) in enumerate(updates.items(), 1):
            set_parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(id)

        await conn.execute(
            f"UPDATE contact_channels SET {', '.join(set_parts)} WHERE id = ${len(values)}",
            *values
        )
        return await channel_get(id)


async def channel_delete(id: int) -> bool:
    """Delete channel by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM contact_channels WHERE id = $1", id)
        return result.split()[-1] != '0'


async def channel_set_primary(id: int) -> Optional[dict]:
    """Set channel as primary (unsets others of same type)."""
    return await channel_update(id, is_primary=True)


# =============================================================================
# PROJECT ASSIGNMENTS CRUD
# =============================================================================

async def assignment_add(
    contact_id: int,
    project_id: int,
    role_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workdays_allocated: Optional[int] = None,
    notes: Optional[str] = None
) -> dict:
    """Add a project assignment to a contact."""
    role = await role_get(role_code)
    if not role:
        raise ValueError(f"Invalid role_code: {role_code}")

    async with get_db() as conn:
        row = await conn.fetchrow("SELECT id FROM projects WHERE id = $1", project_id)
        if not row:
            raise ValueError(f"Project {project_id} not found")

        row = await conn.fetchrow(
            """
            INSERT INTO contact_projects
            (contact_id, project_id, role_code, start_date, end_date, workdays_allocated, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            contact_id, project_id, role_code.upper(), start_date, end_date, workdays_allocated, notes
        )
        return await assignment_get(row["id"])


async def assignment_get(id: int) -> Optional[dict]:
    """Get assignment by id."""
    async with get_db() as conn:
        row = await conn.fetchrow("SELECT * FROM v_contact_projects WHERE id = $1", id)
        return dict(row) if row else None


async def assignment_list(
    contact_id: Optional[int] = None,
    project_id: Optional[int] = None,
    role_code: Optional[str] = None,
    active_only: bool = True
) -> list[dict]:
    """List project assignments with optional filters."""
    async with get_db() as conn:
        conditions = []
        params = []
        idx = 1

        if contact_id:
            conditions.append(f"contact_id = ${idx}")
            params.append(contact_id)
            idx += 1
        if project_id:
            conditions.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if role_code:
            conditions.append(f"role_code = ${idx}")
            params.append(role_code.upper())
            idx += 1
        if active_only:
            conditions.append("is_active = TRUE")

        query = "SELECT * FROM v_contact_projects"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def assignment_update(id: int, **kwargs) -> Optional[dict]:
    """Update assignment by id."""
    allowed_fields = {'role_code', 'start_date', 'end_date', 'is_active', 'workdays_allocated', 'notes'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await assignment_get(id)

    if 'role_code' in updates:
        updates['role_code'] = updates['role_code'].upper()
        if not await role_get(updates['role_code']):
            raise ValueError(f"Invalid role_code: {updates['role_code']}")

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    values.append(id)

    async with get_db() as conn:
        await conn.execute(
            f"UPDATE contact_projects SET {', '.join(set_parts)} WHERE id = ${len(values)}",
            *values
        )
        return await assignment_get(id)


async def assignment_delete(id: int) -> bool:
    """Delete assignment by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM contact_projects WHERE id = $1", id)
        return result.split()[-1] != '0'


# =============================================================================
# ROLES (Read-only)
# =============================================================================

async def role_list(category: Optional[str] = None) -> list[dict]:
    """List all project roles."""
    async with get_db() as conn:
        if category:
            if category not in ROLE_CATEGORIES:
                raise ValueError(f"Invalid category. Must be one of: {ROLE_CATEGORIES}")
            rows = await conn.fetch(
                "SELECT * FROM project_roles WHERE role_category = $1 ORDER BY role_code",
                category
            )
        else:
            rows = await conn.fetch("SELECT * FROM project_roles ORDER BY role_category, role_code")

        return [dict(row) for row in rows]


async def role_get(code: str) -> Optional[dict]:
    """Get role by code."""
    async with get_db() as conn:
        row = await conn.fetchrow("SELECT * FROM project_roles WHERE role_code = $1", code.upper())
        return dict(row) if row else None


# =============================================================================
# PROJECT TEAM (convenience functions)
# =============================================================================

async def get_project_team(project_id: int) -> list[dict]:
    """Get full team for a project with contact details."""
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM v_project_team WHERE project_id = $1",
            project_id
        )
        return [dict(row) for row in rows]


async def get_contact_projects(contact_id: int) -> list[dict]:
    """Get all projects for a contact."""
    return await assignment_list(contact_id=contact_id)
