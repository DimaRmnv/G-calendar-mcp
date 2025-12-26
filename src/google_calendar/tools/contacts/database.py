"""
Database management for contacts using PostgreSQL.

Uses shared connection pool from google_calendar.db.connection.
Schema managed via google_calendar/db/schema.sql.

Tables: contacts, contact_channels, project_roles, contact_projects
Views: v_contacts_full, v_project_team, v_contact_projects
"""

from typing import Optional

# Optional fuzzy search - fallback to ILIKE if not installed
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

from google_calendar.db.connection import get_db, check_db_exists


# Valid values for CHECK constraints
ORGANIZATION_TYPES = (
    # Funding & Development
    'donor', 'dfi',
    # Financial Institutions
    'bank', 'mfi', 'nbfi',
    # Public Sector
    'government', 'regulator',
    # Private Sector
    'client', 'vendor', 'consulting',
    # Non-profit & Associations
    'ngo', 'association', 'training_provider',
    # Relationships
    'partner', 'other'
)
PREFERRED_CHANNELS = ('email', 'telegram', 'teams', 'phone', 'whatsapp')
CHANNEL_TYPES = (
    'email', 'phone', 'telegram_id', 'telegram_username', 'telegram_chat_id',
    'teams_id', 'teams_chat_id', 'whatsapp', 'linkedin', 'skype', 'google_calendar'
)
ROLE_CATEGORIES = ('consultant', 'client', 'donor', 'partner')

# Field sets for token optimization
CONTACT_COMPACT_FIELDS = """
    id, first_name, last_name, display_name,
    organization_name, job_title, country, preferred_channel
"""

# Standard project roles (for reference - inserted via schema.sql)
STANDARD_ROLES = [
    ('TL', 'Team Leader', 'Руководитель группы', 'consultant', 'Overall project leadership'),
    ('DTL', 'Deputy Team Leader', 'Заместитель руководителя', 'consultant', 'Supports TL'),
    ('KE', 'Key Expert', 'Ключевой эксперт', 'consultant', 'Named expert in contract'),
    ('NKE', 'Non-Key Expert', 'Неключевой эксперт', 'consultant', 'Short-term expert'),
    ('PM', 'Project Manager', 'Менеджер проекта', 'consultant', 'Administrative management'),
    ('BSM', 'Backstopping Manager', 'Бэкстоппинг менеджер', 'consultant', 'HQ support'),
    ('JE', 'Junior Expert', 'Младший эксперт', 'consultant', 'Entry-level'),
    ('LA', 'Local Assistant', 'Локальный ассистент', 'consultant', 'In-country support'),
    ('INT', 'Interpreter/Translator', 'Переводчик', 'consultant', 'Language support'),
    ('CD', 'Client Director', 'Директор клиента', 'client', 'Decision maker'),
    ('CPM', 'Client Project Manager', 'Менеджер проекта клиента', 'client', 'Day-to-day contact'),
    ('PIU', 'PIU Coordinator', 'Координатор ГРП', 'client', 'Implementation unit lead'),
    ('CP', 'Counterpart', 'Контрагент', 'client', 'Working-level staff'),
    ('BEN', 'Beneficiary', 'Бенефициар', 'client', 'End beneficiary'),
    ('DO', 'Donor Officer', 'Представитель донора', 'donor', 'Main donor contact'),
    ('DPM', 'Donor Project Manager', 'Менеджер проекта донора', 'donor', 'Donor staff'),
    ('TA', 'Technical Advisor', 'Технический советник', 'donor', 'Technical oversight'),
    ('PC', 'Partner Consultant', 'Консультант-партнер', 'partner', 'Partner organization'),
    ('SUB', 'Subcontractor', 'Субподрядчик', 'partner', 'Subcontracted entity'),
]


async def database_exists() -> bool:
    """Check if database exists."""
    return await check_db_exists()


async def contacts_tables_exist() -> bool:
    """Check if contacts tables exist in database."""
    async with get_db() as conn:
        row = await conn.fetchrow("""
            SELECT EXISTS (
                SELECT FROM pg_tables
                WHERE schemaname = 'public' AND tablename = 'contacts'
            )
        """)
        return row[0] if row else False


async def ensure_contacts_schema() -> bool:
    """Ensure contacts tables exist. Schema managed via schema.sql."""
    return await contacts_tables_exist()


def init_contacts_schema() -> None:
    """Placeholder - schema managed via schema.sql in workflow."""
    pass


def get_connection():
    """Placeholder for compatibility - use async get_db() instead."""
    raise NotImplementedError("Use async get_db() from db.connection")


# =============================================================================
# CONTACTS CRUD
# =============================================================================

async def contact_add(
    first_name: str,
    last_name: str,
    organization_id: Optional[int] = None,
    org_notes: Optional[str] = None,
    job_title: Optional[str] = None,
    department: Optional[str] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
    timezone: Optional[str] = None,
    preferred_channel: str = 'email',
    preferred_language: str = 'en',
    context: Optional[str] = None,
    relationship_type: Optional[str] = None,
    relationship_strength: Optional[str] = None,
    last_interaction_date: Optional[str] = None,
    notes: Optional[str] = None
) -> dict:
    """Create a new contact. Returns CONTACT_COMPACT."""
    if preferred_channel not in PREFERRED_CHANNELS:
        raise ValueError(f"Invalid preferred_channel. Must be one of: {PREFERRED_CHANNELS}")

    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO contacts (
                first_name, last_name, organization_id, org_notes,
                job_title, department, country, city, timezone,
                preferred_channel, preferred_language, context,
                relationship_type, relationship_strength, last_interaction_date, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            RETURNING id
            """,
            first_name, last_name, organization_id, org_notes,
            job_title, department, country, city, timezone,
            preferred_channel, preferred_language, context,
            relationship_type, relationship_strength, last_interaction_date, notes
        )
        # Get organization_name if organization_id provided
        org_name = None
        if organization_id:
            org_row = await conn.fetchrow(
                "SELECT name FROM organizations WHERE id = $1", organization_id
            )
            org_name = org_row['name'] if org_row else None

        # Return CONTACT_COMPACT
        return {
            "id": row['id'],
            "first_name": first_name,
            "last_name": last_name,
            "display_name": f"{first_name} {last_name}",
            "organization_name": org_name,
            "job_title": job_title,
            "country": country,
            "preferred_channel": preferred_channel
        }


async def get_contact_channels_compact(contact_id: int) -> list[dict]:
    """Get channels for contact in compact format.

    Returns: [{id, channel_type, channel_value, is_primary}]
    """
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT id, channel_type, channel_value, is_primary
            FROM contact_channels
            WHERE contact_id = $1
            ORDER BY is_primary DESC, channel_type
            """,
            contact_id
        )
        return [dict(row) for row in rows]


async def get_contact_projects_compact(contact_id: int) -> list[dict]:
    """Get projects for contact in compact format.

    Returns: [{project_id, project_code, role_name}]
    """
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT cp.project_id, p.code as project_code, cp.role_name
            FROM contact_projects cp
            LEFT JOIN projects p ON cp.project_id = p.id
            WHERE cp.contact_id = $1 AND cp.is_active = TRUE
            ORDER BY p.code
            """,
            contact_id
        )
        return [dict(row) for row in rows]


async def contact_get(
    id: Optional[int] = None,
    email: Optional[str] = None,
    telegram: Optional[str] = None,
    phone: Optional[str] = None,
    include_channels: bool = False,
    include_projects: bool = False
) -> Optional[dict]:
    """Get contact by id or by channel value. Returns CONTACT_FULL format.

    Args:
        id: Contact ID
        email: Email address
        telegram: Telegram username or ID
        phone: Phone number
        include_channels: If True, include channels[] array
        include_projects: If True, include projects[] array
    """
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

        if not row:
            return None

        result = dict(row)

        if include_channels:
            result["channels"] = await get_contact_channels_compact(result["id"])

        if include_projects:
            result["projects"] = await get_contact_projects_compact(result["id"])

        return result


async def contact_list(
    organization: Optional[str] = None,
    country: Optional[str] = None,
    project_id: Optional[int] = None,
    role_name: Optional[str] = None,
    preferred_channel: Optional[str] = None,
    org_type: Optional[str] = None,
    active_only: bool = True
) -> list[dict]:
    """List contacts with optional filters. Returns CONTACT_COMPACT format."""
    async with get_db() as conn:
        if project_id is not None:
            # Use project team view (already optimized)
            if role_name:
                rows = await conn.fetch(
                    "SELECT * FROM v_project_team WHERE project_id = $1 AND project_role ILIKE $2",
                    project_id, f"%{role_name}%"
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM v_project_team WHERE project_id = $1",
                    project_id
                )
        else:
            # Build dynamic query with COMPACT fields
            conditions = []
            params = []
            param_idx = 1

            if organization:
                conditions.append(f"organization_name ILIKE ${param_idx}")
                params.append(f"%{organization}%")
                param_idx += 1
            if org_type:
                conditions.append(f"org_type = ${param_idx}")
                params.append(org_type)
                param_idx += 1
            if country:
                conditions.append(f"country = ${param_idx}")
                params.append(country)
                param_idx += 1
            if preferred_channel:
                conditions.append(f"preferred_channel = ${param_idx}")
                params.append(preferred_channel)
                param_idx += 1

            # v_contacts_full already filters is_active = TRUE
            query = f"SELECT {CONTACT_COMPACT_FIELDS} FROM v_contacts_full"

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY last_name, first_name"

            rows = await conn.fetch(query, *params)

        return [dict(row) for row in rows]


async def contact_update(id: int, **kwargs) -> Optional[dict]:
    """Update contact by id. Returns CONTACT_COMPACT."""
    allowed_fields = {
        'first_name', 'last_name', 'organization_id', 'org_notes',
        'job_title', 'department', 'country', 'city', 'timezone',
        'preferred_channel', 'preferred_language', 'context',
        'relationship_type', 'relationship_strength', 'last_interaction_date',
        'notes', 'is_active'
    }
    # Fields that can be explicitly set to NULL
    nullable_fields = {
        'organization_id', 'org_notes', 'department', 'city', 'timezone',
        'context', 'relationship_type', 'relationship_strength',
        'last_interaction_date', 'notes'
    }
    updates = {k: v for k, v in kwargs.items()
               if k in allowed_fields and (v is not None or k in nullable_fields)}

    if 'preferred_channel' in updates and updates['preferred_channel'] not in PREFERRED_CHANNELS:
        raise ValueError(f"Invalid preferred_channel. Must be one of: {PREFERRED_CHANNELS}")

    async with get_db() as conn:
        if updates:
            set_parts = []
            values = []
            for i, (k, v) in enumerate(updates.items(), 1):
                set_parts.append(f"{k} = ${i}")
                values.append(v)

            values.append(id)
            set_clause = ", ".join(set_parts)

            result = await conn.execute(
                f"UPDATE contacts SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(values)}",
                *values
            )
            if result == "UPDATE 0":
                return None

        # Return CONTACT_COMPACT
        row = await conn.fetchrow(
            f"SELECT {CONTACT_COMPACT_FIELDS} FROM v_contacts_full WHERE id = $1",
            id
        )
        return dict(row) if row else None


async def contact_delete(id: int) -> bool:
    """Delete contact by id (cascades to channels and project assignments)."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM contacts WHERE id = $1", id)
        return result != "DELETE 0"


async def contact_search(
    query: str,
    limit: int = 20,
    threshold: int = 60
) -> list[dict]:
    """
    Search contacts across multiple fields including project assignments.

    Searchable fields:
        1. Name: first_name, last_name, display_name
        2. Organization: organization, country, job_title
        3. Channels: email, telegram_username (@), phone
        4. Projects: project code, project description

    Args:
        query: Search string (case-insensitive)
        limit: Max results (default 20)
        threshold: Min fuzzy score 0-100 (default 60)

    Returns:
        List of contacts with match_score and matched_field
    """
    query = query.strip()
    if not query:
        return []

    if FUZZY_AVAILABLE:
        return await _contact_search_fuzzy(query, limit, threshold)
    else:
        return await _contact_search_like(query, limit)


async def _contact_search_like(query: str, limit: int = 20) -> list[dict]:
    """ILIKE-based search (fallback when rapidfuzz not available). Returns CONTACT_COMPACT + email + score."""
    query = query.lstrip('@')
    search_pattern = f"%{query}%"

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (cf.id)
                cf.id, cf.first_name, cf.last_name, cf.display_name,
                cf.organization_name, cf.job_title, cf.country, cf.preferred_channel,
                cf.primary_email
            FROM v_contacts_full cf
            LEFT JOIN contact_channels cc ON cf.id = cc.contact_id
            LEFT JOIN contact_projects cp ON cf.id = cp.contact_id AND cp.is_active = TRUE
            LEFT JOIN projects p ON cp.project_id = p.id AND p.is_active = TRUE
            WHERE cf.display_name ILIKE $1
               OR cf.first_name ILIKE $1
               OR cf.last_name ILIKE $1
               OR cf.organization_name ILIKE $1
               OR cf.country ILIKE $1
               OR cf.job_title ILIKE $1
               OR cc.channel_value ILIKE $1
               OR p.code ILIKE $1
               OR p.description ILIKE $1
            ORDER BY cf.id, cf.display_name
            LIMIT $2
            """,
            search_pattern, limit
        )

        results = []
        for row in rows:
            item = dict(row)
            item['match_score'] = 100.0
            results.append(item)
        return results


async def _contact_search_fuzzy(query: str, limit: int = 20, threshold: int = 60) -> list[dict]:
    """Fuzzy search using rapidfuzz. Returns CONTACT_COMPACT + email + score."""
    query_clean = query.lstrip('@').lower()

    async with get_db() as conn:
        rows = await conn.fetch("""
            SELECT
                cf.id, cf.first_name, cf.last_name, cf.display_name,
                cf.organization_name, cf.job_title, cf.country,
                cf.preferred_channel, cf.primary_email,
                STRING_AGG(DISTINCT
                    CASE
                        WHEN cc.channel_type = 'telegram_username' THEN '@' || cc.channel_value
                        ELSE cc.channel_value
                    END,
                    '||'
                ) as all_channels,
                STRING_AGG(DISTINCT cc.channel_type || ':' || cc.channel_value, '||') as channel_details,
                STRING_AGG(DISTINCT p.code, '||') as project_codes,
                STRING_AGG(DISTINCT p.description, '||') as project_descriptions
            FROM v_contacts_full cf
            LEFT JOIN contact_channels cc ON cf.id = cc.contact_id
            LEFT JOIN contact_projects cp ON cf.id = cp.contact_id AND cp.is_active = TRUE
            LEFT JOIN projects p ON cp.project_id = p.id AND p.is_active = TRUE
            GROUP BY cf.id, cf.first_name, cf.last_name, cf.display_name,
                     cf.organization_name, cf.job_title, cf.country,
                     cf.preferred_channel, cf.primary_email
        """)

    contacts = [dict(row) for row in rows]
    if not contacts:
        return []

    results = []

    for contact in contacts:
        search_fields = {
            'name': contact.get('display_name') or '',
            'first_name': contact.get('first_name') or '',
            'last_name': contact.get('last_name') or '',
            'organization': contact.get('organization_name') or '',
            'country': contact.get('country') or '',
            'job_title': contact.get('job_title') or '',
        }

        # Parse channels
        channel_details = contact.get('channel_details') or ''
        if channel_details:
            for ch in channel_details.split('||'):
                if ':' in ch:
                    ch_type, ch_value = ch.split(':', 1)
                    if ch_type == 'email':
                        search_fields['email'] = ch_value
                    elif ch_type == 'telegram_username':
                        search_fields['telegram'] = f'@{ch_value}'
                    elif ch_type == 'phone':
                        search_fields['phone'] = ch_value

        # Add project fields
        project_codes = contact.get('project_codes') or ''
        project_descriptions = contact.get('project_descriptions') or ''
        if project_codes:
            search_fields['project_code'] = project_codes.replace('||', ' ')
        if project_descriptions:
            search_fields['project'] = project_descriptions.replace('||', ' ')

        # Find best match
        best_score = 0

        for field_name, field_value in search_fields.items():
            if not field_value:
                continue

            score_partial = fuzz.partial_ratio(query_clean, field_value.lower())
            score_token = fuzz.token_set_ratio(query_clean, field_value.lower())
            score = max(score_partial, score_token)

            if score > best_score:
                best_score = score

        if best_score >= threshold:
            # Return CONTACT_COMPACT + email + score
            contact_result = {
                "id": contact["id"],
                "first_name": contact.get("first_name"),
                "last_name": contact.get("last_name"),
                "display_name": contact.get("display_name"),
                "organization_name": contact.get("organization_name"),
                "job_title": contact.get("job_title"),
                "country": contact.get("country"),
                "preferred_channel": contact.get("preferred_channel"),
                "primary_email": contact.get("primary_email"),
                "match_score": float(best_score)
            }
            results.append(contact_result)

    results.sort(key=lambda x: (-x['match_score'], x.get('display_name', '')))
    return results[:limit]


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

    # Clean telegram username
    if channel_type == 'telegram_username':
        channel_value = channel_value.lstrip('@')

    async with get_db() as conn:
        # If setting as primary, unset other primaries of same type
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
            "id": row['id'],
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
    """Update channel by id. Returns compact format."""
    allowed_fields = {'channel_value', 'channel_label', 'is_primary', 'notes'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    current = await channel_get(id)
    if not current:
        return None

    async with get_db() as conn:
        if updates:
            # If setting as primary, unset other primaries
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
            set_clause = ", ".join(set_parts)

            await conn.execute(f"UPDATE contact_channels SET {set_clause} WHERE id = ${len(values)}", *values)

        # Return compact
        row = await conn.fetchrow(
            "SELECT id, contact_id, channel_type, channel_value, is_primary FROM contact_channels WHERE id = $1",
            id
        )
        return dict(row) if row else None


async def channel_delete(id: int) -> bool:
    """Delete channel by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM contact_channels WHERE id = $1", id)
        return result != "DELETE 0"


async def channel_set_primary(id: int) -> Optional[dict]:
    """Set channel as primary (unsets others of same type)."""
    return await channel_update(id, is_primary=True)


# =============================================================================
# PROJECT ASSIGNMENTS CRUD
# =============================================================================

async def assignment_add(
    contact_id: int,
    project_id: int,
    role_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workdays_allocated: Optional[int] = None,
    notes: Optional[str] = None
) -> dict:
    """Add a project assignment to a contact. Returns compact format."""
    async with get_db() as conn:
        # Validate project exists and get code
        project = await conn.fetchrow("SELECT id, code FROM projects WHERE id = $1", project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        row = await conn.fetchrow(
            """
            INSERT INTO contact_projects
            (contact_id, project_id, role_name, start_date, end_date, workdays_allocated, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            contact_id, project_id, role_name, start_date, end_date, workdays_allocated, notes
        )
        # Return compact
        return {
            "id": row['id'],
            "contact_id": contact_id,
            "project_id": project_id,
            "project_code": project['code'],
            "role_name": role_name
        }


async def assignment_get(id: int) -> Optional[dict]:
    """Get assignment by id."""
    async with get_db() as conn:
        row = await conn.fetchrow("SELECT * FROM v_contact_projects WHERE id = $1", id)
        return dict(row) if row else None


async def assignment_list(
    contact_id: Optional[int] = None,
    project_id: Optional[int] = None,
    role_name: Optional[str] = None,
    active_only: bool = True
) -> list[dict]:
    """List project assignments with optional filters. Returns compact format."""
    async with get_db() as conn:
        conditions = []
        params = []
        param_idx = 1

        if contact_id:
            conditions.append(f"contact_id = ${param_idx}")
            params.append(contact_id)
            param_idx += 1
        if project_id:
            conditions.append(f"project_id = ${param_idx}")
            params.append(project_id)
            param_idx += 1
        if role_name:
            conditions.append(f"role_name ILIKE ${param_idx}")
            params.append(f"%{role_name}%")
            param_idx += 1
        if active_only:
            conditions.append("is_active = TRUE")

        # Return compact fields only
        query = "SELECT id, project_id, project_code, role_name, is_active FROM v_contact_projects"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def assignment_update(id: int, **kwargs) -> Optional[dict]:
    """Update assignment by id."""
    allowed_fields = {'role_name', 'start_date', 'end_date', 'is_active', 'workdays_allocated', 'notes'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not updates:
        return await assignment_get(id)

    set_parts = []
    values = []
    for i, (k, v) in enumerate(updates.items(), 1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)

    values.append(id)
    set_clause = ", ".join(set_parts)

    async with get_db() as conn:
        result = await conn.execute(f"UPDATE contact_projects SET {set_clause} WHERE id = ${len(values)}", *values)
        if result == "UPDATE 0":
            return None

    return await assignment_get(id)


async def assignment_delete(id: int) -> bool:
    """Delete assignment by id."""
    async with get_db() as conn:
        result = await conn.execute("DELETE FROM contact_projects WHERE id = $1", id)
        return result != "DELETE 0"


# =============================================================================
# ROLES (Read-only, populated via schema.sql)
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


# =============================================================================
# Compatibility placeholders
# =============================================================================

def get_database_path():
    """Placeholder - not used with PostgreSQL."""
    return None
