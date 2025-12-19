"""
Database management for contacts.

Extends the existing time_tracking.db with contacts tables.
Tables: contacts, contact_channels, project_roles, contact_projects
Database location: ~/.mcp/google-calendar/time_tracking.db
"""

import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

# Optional fuzzy search - fallback to LIKE if not installed
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

from google_calendar.utils.config import get_app_dir


DATABASE_NAME = "time_tracking.db"

# Valid values for CHECK constraints
ORGANIZATION_TYPES = ('donor', 'client', 'partner', 'bfc', 'government', 'bank', 'mfi', 'other')
PREFERRED_CHANNELS = ('email', 'telegram', 'teams', 'phone', 'whatsapp')
CHANNEL_TYPES = (
    'email', 'phone', 'telegram_id', 'telegram_username', 'telegram_chat_id',
    'teams_id', 'teams_chat_id', 'whatsapp', 'linkedin', 'skype', 'google_calendar'
)
ROLE_CATEGORIES = ('consultant', 'client', 'donor', 'partner')

# Standard project roles
STANDARD_ROLES = [
    # Consultant team
    ('TL', 'Team Leader', 'Руководитель группы', 'consultant', 'Overall project leadership'),
    ('DTL', 'Deputy Team Leader', 'Заместитель руководителя', 'consultant', 'Supports TL'),
    ('KE', 'Key Expert', 'Ключевой эксперт', 'consultant', 'Named expert in contract'),
    ('NKE', 'Non-Key Expert', 'Неключевой эксперт', 'consultant', 'Short-term expert'),
    ('PM', 'Project Manager', 'Менеджер проекта', 'consultant', 'Administrative management'),
    ('BSM', 'Backstopping Manager', 'Бэкстоппинг менеджер', 'consultant', 'HQ support'),
    ('JE', 'Junior Expert', 'Младший эксперт', 'consultant', 'Entry-level'),
    ('LA', 'Local Assistant', 'Локальный ассистент', 'consultant', 'In-country support'),
    ('INT', 'Interpreter/Translator', 'Переводчик', 'consultant', 'Language support'),
    # Client side
    ('CD', 'Client Director', 'Директор клиента', 'client', 'Decision maker'),
    ('CPM', 'Client Project Manager', 'Менеджер проекта клиента', 'client', 'Day-to-day contact'),
    ('PIU', 'PIU Coordinator', 'Координатор ГРП', 'client', 'Implementation unit lead'),
    ('CP', 'Counterpart', 'Контрагент', 'client', 'Working-level staff'),
    ('BEN', 'Beneficiary', 'Бенефициар', 'client', 'End beneficiary'),
    # Donor side
    ('DO', 'Donor Officer', 'Представитель донора', 'donor', 'Main donor contact'),
    ('DPM', 'Donor Project Manager', 'Менеджер проекта донора', 'donor', 'Donor staff'),
    ('TA', 'Technical Advisor', 'Технический советник', 'donor', 'Technical oversight'),
    # Partners
    ('PC', 'Partner Consultant', 'Консультант-партнер', 'partner', 'Partner organization'),
    ('SUB', 'Subcontractor', 'Субподрядчик', 'partner', 'Subcontracted entity'),
]


def get_database_path() -> Path:
    """Get path to database (shared with time_tracking)."""
    return get_app_dir() / DATABASE_NAME


def database_exists() -> bool:
    """Check if database file exists."""
    return get_database_path().exists()


def contacts_tables_exist() -> bool:
    """Check if contacts tables already exist in database."""
    if not database_exists():
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'"
        )
        return cursor.fetchone() is not None


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


def init_contacts_schema() -> None:
    """Initialize contacts tables in the database."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # ---------------------------------------------------------------------
        # CONTACTS - Core contact information
        # ---------------------------------------------------------------------
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Basic info
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                display_name TEXT GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
                
                -- Organization
                organization TEXT,
                organization_type TEXT CHECK(organization_type IN 
                    {ORGANIZATION_TYPES}),
                job_title TEXT,
                department TEXT,
                
                -- Location & Time
                country TEXT,
                city TEXT,
                timezone TEXT,
                
                -- Communication preferences
                preferred_channel TEXT DEFAULT 'email' CHECK(preferred_channel IN 
                    {PREFERRED_CHANNELS}),
                preferred_language TEXT DEFAULT 'en',
                
                -- Notes
                notes TEXT,
                
                -- Metadata
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)

        # ---------------------------------------------------------------------
        # CONTACT_CHANNELS - All contact methods
        # ---------------------------------------------------------------------
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS contact_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                
                channel_type TEXT NOT NULL CHECK(channel_type IN 
                    {CHANNEL_TYPES}),
                channel_value TEXT NOT NULL,
                channel_label TEXT,
                is_primary BOOLEAN DEFAULT FALSE,
                notes TEXT,
                
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                UNIQUE(contact_id, channel_type, channel_value)
            )
        """)

        # ---------------------------------------------------------------------
        # PROJECT_ROLES - Standard consulting project roles
        # ---------------------------------------------------------------------
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS project_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_code TEXT UNIQUE NOT NULL,
                role_name_en TEXT NOT NULL,
                role_name_ru TEXT,
                role_category TEXT CHECK(role_category IN {ROLE_CATEGORIES}),
                description TEXT
            )
        """)

        # Insert standard roles
        for role in STANDARD_ROLES:
            cursor.execute(
                """
                INSERT OR IGNORE INTO project_roles 
                (role_code, role_name_en, role_name_ru, role_category, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                role
            )

        # ---------------------------------------------------------------------
        # CONTACT_PROJECTS - Links contacts to projects with roles
        # ---------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contact_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                role_code TEXT NOT NULL,
                
                start_date DATE,
                end_date DATE,
                is_active BOOLEAN DEFAULT TRUE,
                workdays_allocated INTEGER,
                notes TEXT,
                
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                FOREIGN KEY (role_code) REFERENCES project_roles(role_code),
                FOREIGN KEY (project_id) REFERENCES projects(id),
                UNIQUE(contact_id, project_id, role_code)
            )
        """)

        # ---------------------------------------------------------------------
        # INDEXES
        # ---------------------------------------------------------------------
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(first_name, last_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(organization)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_display ON contacts(display_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_country ON contacts(country)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channels_type ON contact_channels(channel_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channels_value ON contact_channels(channel_value)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_projects_project ON contact_projects(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_projects_contact ON contact_projects(contact_id)")

        # ---------------------------------------------------------------------
        # VIEWS
        # ---------------------------------------------------------------------
        
        # Full contact with primary channels
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS v_contacts_full AS
            SELECT 
                c.id,
                c.first_name,
                c.last_name,
                c.display_name,
                c.organization,
                c.organization_type,
                c.job_title,
                c.department,
                c.country,
                c.city,
                c.timezone,
                c.preferred_channel,
                c.preferred_language,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'email' AND is_primary = 1 LIMIT 1) as primary_email,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'phone' AND is_primary = 1 LIMIT 1) as primary_phone,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'telegram_chat_id' LIMIT 1) as telegram_chat_id,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'telegram_username' LIMIT 1) as telegram_username,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'teams_chat_id' LIMIT 1) as teams_chat_id,
                c.notes,
                c.created_at,
                c.updated_at
            FROM contacts c
            WHERE c.is_active = 1
        """)

        # Project team view
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS v_project_team AS
            SELECT 
                cp.project_id,
                c.id as contact_id,
                c.display_name,
                c.organization,
                c.job_title,
                pr.role_code,
                pr.role_name_en as project_role,
                pr.role_category,
                c.preferred_channel,
                c.preferred_language,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'email' AND is_primary = 1 LIMIT 1) as email,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'telegram_chat_id' LIMIT 1) as telegram_chat_id,
                (SELECT channel_value FROM contact_channels WHERE contact_id = c.id 
                 AND channel_type = 'teams_chat_id' LIMIT 1) as teams_chat_id
            FROM contact_projects cp
            JOIN contacts c ON cp.contact_id = c.id
            JOIN project_roles pr ON cp.role_code = pr.role_code
            WHERE cp.is_active = 1 AND c.is_active = 1
            ORDER BY 
                CASE pr.role_category 
                    WHEN 'donor' THEN 1 
                    WHEN 'client' THEN 2 
                    WHEN 'consultant' THEN 3 
                    WHEN 'partner' THEN 4 
                END
        """)

        # Contact projects view
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS v_contact_projects AS
            SELECT 
                cp.id,
                cp.contact_id,
                c.display_name as contact_name,
                c.organization,
                cp.project_id,
                cp.role_code,
                pr.role_name_en,
                pr.role_name_ru,
                pr.role_category,
                cp.is_active,
                cp.workdays_allocated,
                cp.start_date,
                cp.end_date,
                cp.notes
            FROM contact_projects cp
            JOIN contacts c ON cp.contact_id = c.id
            JOIN project_roles pr ON cp.role_code = pr.role_code
        """)


def ensure_contacts_schema() -> bool:
    """Ensure contacts tables exist. Returns True if newly created."""
    if not database_exists():
        # Database doesn't exist - need to init time_tracking first
        raise RuntimeError(
            "Database does not exist. Enable time_tracking first to create the database, "
            "or run time_tracking init."
        )
    
    newly_created = not contacts_tables_exist()
    if newly_created:
        init_contacts_schema()
    return newly_created


# =============================================================================
# CONTACTS CRUD
# =============================================================================

def contact_add(
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
    # Validate enums
    if organization_type and organization_type not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if preferred_channel not in PREFERRED_CHANNELS:
        raise ValueError(f"Invalid preferred_channel. Must be one of: {PREFERRED_CHANNELS}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO contacts (
                first_name, last_name, organization, organization_type,
                job_title, department, country, city, timezone,
                preferred_channel, preferred_language, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (first_name, last_name, organization, organization_type,
             job_title, department, country, city, timezone,
             preferred_channel, preferred_language, notes)
        )
        new_id = cursor.lastrowid
    # Fetch after commit
    return contact_get(id=new_id)


def contact_get(
    id: Optional[int] = None,
    email: Optional[str] = None,
    telegram: Optional[str] = None,
    phone: Optional[str] = None
) -> Optional[dict]:
    """Get contact by id or by channel value."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if id is not None:
            cursor.execute("SELECT * FROM v_contacts_full WHERE id = ?", (id,))
        elif email is not None:
            cursor.execute(
                """
                SELECT cf.* FROM v_contacts_full cf
                JOIN contact_channels cc ON cf.id = cc.contact_id
                WHERE cc.channel_type = 'email' AND cc.channel_value = ?
                """,
                (email,)
            )
        elif telegram is not None:
            # Search by telegram_id, telegram_username, or telegram_chat_id
            cursor.execute(
                """
                SELECT cf.* FROM v_contacts_full cf
                JOIN contact_channels cc ON cf.id = cc.contact_id
                WHERE cc.channel_type IN ('telegram_id', 'telegram_username', 'telegram_chat_id')
                  AND cc.channel_value = ?
                """,
                (telegram.lstrip('@'),)
            )
        elif phone is not None:
            cursor.execute(
                """
                SELECT cf.* FROM v_contacts_full cf
                JOIN contact_channels cc ON cf.id = cc.contact_id
                WHERE cc.channel_type = 'phone' AND cc.channel_value = ?
                """,
                (phone,)
            )
        else:
            return None
        
        row = cursor.fetchone()
        return dict(row) if row else None


def contact_list(
    organization: Optional[str] = None,
    organization_type: Optional[str] = None,
    country: Optional[str] = None,
    project_id: Optional[int] = None,
    role_code: Optional[str] = None,
    active_only: bool = True
) -> list[dict]:
    """List contacts with optional filters."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if project_id is not None:
            # Use project team view
            query = "SELECT * FROM v_project_team WHERE project_id = ?"
            params = [project_id]
            if role_code:
                query += " AND role_code = ?"
                params.append(role_code)
            cursor.execute(query, params)
        else:
            # Use full contacts view
            base = "v_contacts_full" if active_only else "contacts"
            conditions = []
            params = []
            
            if organization:
                conditions.append("organization LIKE ?")
                params.append(f"%{organization}%")
            if organization_type:
                conditions.append("organization_type = ?")
                params.append(organization_type)
            if country:
                conditions.append("country = ?")
                params.append(country)
            if not active_only:
                pass  # Include all
            
            query = f"SELECT * FROM {base}"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY display_name"
            
            cursor.execute(query, params)
        
        return [dict(row) for row in cursor.fetchall()]


def contact_update(id: int, **kwargs) -> Optional[dict]:
    """Update contact by id."""
    allowed_fields = {
        'first_name', 'last_name', 'organization', 'organization_type',
        'job_title', 'department', 'country', 'city', 'timezone',
        'preferred_channel', 'preferred_language', 'notes', 'is_active'
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}
    
    if not updates:
        return contact_get(id=id)
    
    # Validate enums
    if 'organization_type' in updates and updates['organization_type'] not in ORGANIZATION_TYPES:
        raise ValueError(f"Invalid organization_type. Must be one of: {ORGANIZATION_TYPES}")
    if 'preferred_channel' in updates and updates['preferred_channel'] not in PREFERRED_CHANNELS:
        raise ValueError(f"Invalid preferred_channel. Must be one of: {PREFERRED_CHANNELS}")
    
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE contacts SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        updated = cursor.rowcount > 0
    # Fetch after commit
    if not updated:
        return None
    return contact_get(id=id)


def contact_delete(id: int) -> bool:
    """Delete contact by id (cascades to channels and project assignments)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contacts WHERE id = ?", (id,))
        return cursor.rowcount > 0


def _contact_search_like(query: str, limit: int = 20) -> list[dict]:
    """
    Fallback LIKE-based search when rapidfuzz not available.
    
    Searches: contact fields, channels, and project assignments.
    """
    # Strip @ for telegram username search
    query = query.lstrip('@')
    
    with get_connection() as conn:
        cursor = conn.cursor()
        search_pattern = f"%{query}%"
        
        cursor.execute(
            """
            SELECT 
                cf.*,
                GROUP_CONCAT(DISTINCT p.code) as projects
            FROM v_contacts_full cf
            LEFT JOIN contact_channels cc ON cf.id = cc.contact_id
            LEFT JOIN contact_projects cp ON cf.id = cp.contact_id AND cp.is_active = 1
            LEFT JOIN projects p ON cp.project_id = p.id AND p.is_active = 1
            WHERE cf.display_name LIKE ? COLLATE NOCASE
               OR cf.first_name LIKE ? COLLATE NOCASE
               OR cf.last_name LIKE ? COLLATE NOCASE
               OR cf.organization LIKE ? COLLATE NOCASE
               OR cf.country LIKE ? COLLATE NOCASE
               OR cf.job_title LIKE ? COLLATE NOCASE
               OR cc.channel_value LIKE ? COLLATE NOCASE
               OR p.code LIKE ? COLLATE NOCASE
               OR p.description LIKE ? COLLATE NOCASE
            GROUP BY cf.id
            ORDER BY cf.display_name
            LIMIT ?
            """,
            (search_pattern,) * 9 + (limit,)
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item['match_score'] = 100  # LIKE match
            item['matched_field'] = 'like'
            # Convert projects string to list
            if item.get('projects'):
                item['projects'] = [p.strip() for p in item['projects'].split(',') if p.strip()]
            results.append(item)
        return results


def _contact_search_fuzzy(query: str, limit: int = 20, threshold: int = 60) -> list[dict]:
    """
    Fuzzy search using rapidfuzz.
    
    Search priority:
    1. Contact fields: display_name, first_name, last_name
    2. Organization, country, job_title
    3. Channels: email, telegram, phone
    4. Projects: code, description (via contact_projects)
    """
    query = query.strip()
    if not query:
        return []
    
    # Clean query for telegram search (handle @username)
    query_clean = query.lstrip('@').lower()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Get all active contacts with their channels AND projects
        cursor.execute("""
            SELECT 
                cf.*,
                GROUP_CONCAT(DISTINCT
                    CASE 
                        WHEN cc.channel_type = 'telegram_username' THEN '@' || cc.channel_value
                        ELSE cc.channel_value 
                    END, 
                    '||'
                ) as all_channels,
                GROUP_CONCAT(DISTINCT cc.channel_type || ':' || cc.channel_value, '||') as channel_details,
                GROUP_CONCAT(DISTINCT p.code, '||') as project_codes,
                GROUP_CONCAT(DISTINCT p.description, '||') as project_descriptions
            FROM v_contacts_full cf
            LEFT JOIN contact_channels cc ON cf.id = cc.contact_id
            LEFT JOIN contact_projects cp ON cf.id = cp.contact_id AND cp.is_active = 1
            LEFT JOIN projects p ON cp.project_id = p.id AND p.is_active = 1
            GROUP BY cf.id
        """)
        
        contacts = [dict(row) for row in cursor.fetchall()]
    
    if not contacts:
        return []
    
    results = []
    
    for contact in contacts:
        # Fields to search with priorities
        search_fields = {
            # Priority 1: Name fields
            'name': contact.get('display_name') or '',
            'first_name': contact.get('first_name') or '',
            'last_name': contact.get('last_name') or '',
            # Priority 2: Organization/location
            'organization': contact.get('organization') or '',
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
        best_field = None
        
        for field_name, field_value in search_fields.items():
            if not field_value:
                continue
            
            score_partial = fuzz.partial_ratio(query_clean, field_value.lower())
            score_token = fuzz.token_set_ratio(query_clean, field_value.lower())
            score = max(score_partial, score_token)
            
            if score > best_score:
                best_score = score
                best_field = field_name
        
        if best_score >= threshold:
            contact_result = {k: v for k, v in contact.items() 
                            if k not in ('all_channels', 'channel_details', 
                                        'project_codes', 'project_descriptions')}
            contact_result['match_score'] = best_score
            contact_result['matched_field'] = best_field
            # Add project info for context
            if project_codes:
                contact_result['projects'] = [p for p in project_codes.split('||') if p]
            results.append(contact_result)
    
    results.sort(key=lambda x: (-x['match_score'], x.get('display_name', '')))
    return results[:limit]


def contact_search(
    query: str, 
    limit: int = 20,
    threshold: int = 60
) -> list[dict]:
    """
    Search contacts across multiple fields including project assignments.
    
    Uses rapidfuzz for fuzzy matching if available, 
    falls back to SQL LIKE otherwise.
    
    Searchable fields (priority order):
        1. Name: first_name, last_name, display_name
        2. Organization: organization, country, job_title
        3. Channels: email, telegram_username (@), phone
        4. Projects: project code, project description
    
    Args:
        query: Search string (case-insensitive, fuzzy if rapidfuzz installed)
        limit: Max results (default 20)
        threshold: Min fuzzy score 0-100 (default 60, ignored for LIKE)
    
    Returns:
        List of contacts with:
        - match_score: 0-100 (100 for LIKE matches)
        - matched_field: which field matched
        - projects: list of project codes contact is assigned to
    
    Examples:
        - "Altynbek" → finds by name
        - "CSUM" → finds contacts assigned to CSUM project
        - "@altynbek" → finds by telegram username
        - "Nepal" → finds contacts in Nepal OR on Nepal project
    """
    query = query.strip()
    if not query:
        return []
    
    if FUZZY_AVAILABLE:
        return _contact_search_fuzzy(query, limit, threshold)
    else:
        return _contact_search_like(query, limit)


# =============================================================================
# CHANNELS CRUD
# =============================================================================

def channel_add(
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
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # If setting as primary, unset other primaries of same type
        if is_primary:
            cursor.execute(
                """
                UPDATE contact_channels 
                SET is_primary = 0 
                WHERE contact_id = ? AND channel_type = ?
                """,
                (contact_id, channel_type)
            )
        
        cursor.execute(
            """
            INSERT INTO contact_channels (contact_id, channel_type, channel_value, channel_label, is_primary, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (contact_id, channel_type, channel_value, channel_label, int(is_primary), notes)
        )
        return {
            "id": cursor.lastrowid,
            "contact_id": contact_id,
            "channel_type": channel_type,
            "channel_value": channel_value,
            "channel_label": channel_label,
            "is_primary": is_primary,
            "notes": notes
        }


def channel_list(contact_id: int) -> list[dict]:
    """List all channels for a contact."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM contact_channels WHERE contact_id = ? ORDER BY channel_type, is_primary DESC",
            (contact_id,)
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_primary"] = bool(item["is_primary"])
            results.append(item)
        return results


def channel_get(id: int) -> Optional[dict]:
    """Get channel by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contact_channels WHERE id = ?", (id,))
        row = cursor.fetchone()
        if row:
            item = dict(row)
            item["is_primary"] = bool(item["is_primary"])
            return item
        return None


def channel_update(id: int, **kwargs) -> Optional[dict]:
    """Update channel by id."""
    allowed_fields = {'channel_value', 'channel_label', 'is_primary', 'notes'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}
    
    if not updates:
        return channel_get(id)
    
    # Get current channel info for primary logic
    current = channel_get(id)
    if not current:
        return None
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # If setting as primary, unset other primaries
        if updates.get('is_primary'):
            cursor.execute(
                """
                UPDATE contact_channels 
                SET is_primary = 0 
                WHERE contact_id = ? AND channel_type = ? AND id != ?
                """,
                (current['contact_id'], current['channel_type'], id)
            )
            updates['is_primary'] = 1
        elif 'is_primary' in updates:
            updates['is_primary'] = int(updates['is_primary'])
        
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [id]
        
        cursor.execute(f"UPDATE contact_channels SET {set_clause} WHERE id = ?", values)
    # Fetch after commit
    return channel_get(id)


def channel_delete(id: int) -> bool:
    """Delete channel by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contact_channels WHERE id = ?", (id,))
        return cursor.rowcount > 0


def channel_set_primary(id: int) -> Optional[dict]:
    """Set channel as primary (unsets others of same type)."""
    return channel_update(id, is_primary=True)


# =============================================================================
# PROJECT ASSIGNMENTS CRUD
# =============================================================================

def assignment_add(
    contact_id: int,
    project_id: int,
    role_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workdays_allocated: Optional[int] = None,
    notes: Optional[str] = None
) -> dict:
    """Add a project assignment to a contact."""
    # Validate role exists
    role = role_get(role_code)
    if not role:
        raise ValueError(f"Invalid role_code: {role_code}")
    
    # Validate project exists (if projects table exists)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        )
        if cursor.fetchone():
            cursor.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
            if not cursor.fetchone():
                raise ValueError(f"Project {project_id} not found")
        
        cursor.execute(
            """
            INSERT INTO contact_projects 
            (contact_id, project_id, role_code, start_date, end_date, workdays_allocated, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (contact_id, project_id, role_code.upper(), start_date, end_date, workdays_allocated, notes)
        )
        new_id = cursor.lastrowid
    # Fetch after commit
    return assignment_get(new_id)


def assignment_get(id: int) -> Optional[dict]:
    """Get assignment by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM v_contact_projects WHERE id = ?", (id,))
        row = cursor.fetchone()
        if row:
            item = dict(row)
            item["is_active"] = bool(item["is_active"])
            return item
        return None


def assignment_list(
    contact_id: Optional[int] = None,
    project_id: Optional[int] = None,
    role_code: Optional[str] = None,
    active_only: bool = True
) -> list[dict]:
    """List project assignments with optional filters."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        if contact_id:
            conditions.append("contact_id = ?")
            params.append(contact_id)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if role_code:
            conditions.append("role_code = ?")
            params.append(role_code.upper())
        if active_only:
            conditions.append("is_active = 1")
        
        query = "SELECT * FROM v_contact_projects"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["is_active"] = bool(item["is_active"])
            results.append(item)
        return results


def assignment_update(id: int, **kwargs) -> Optional[dict]:
    """Update assignment by id."""
    allowed_fields = {'role_code', 'start_date', 'end_date', 'is_active', 'workdays_allocated', 'notes'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}
    
    if not updates:
        return assignment_get(id)
    
    if 'role_code' in updates:
        updates['role_code'] = updates['role_code'].upper()
        if not role_get(updates['role_code']):
            raise ValueError(f"Invalid role_code: {updates['role_code']}")
    
    if 'is_active' in updates:
        updates['is_active'] = int(updates['is_active'])
    
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [id]
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE contact_projects SET {set_clause} WHERE id = ?", values)
        updated = cursor.rowcount > 0
    # Fetch after commit
    if not updated:
        return None
    return assignment_get(id)


def assignment_delete(id: int) -> bool:
    """Delete assignment by id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contact_projects WHERE id = ?", (id,))
        return cursor.rowcount > 0


# =============================================================================
# ROLES (Read-only, populated on init)
# =============================================================================

def role_list(category: Optional[str] = None) -> list[dict]:
    """List all project roles."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if category:
            if category not in ROLE_CATEGORIES:
                raise ValueError(f"Invalid category. Must be one of: {ROLE_CATEGORIES}")
            cursor.execute(
                "SELECT * FROM project_roles WHERE role_category = ? ORDER BY role_code",
                (category,)
            )
        else:
            cursor.execute("SELECT * FROM project_roles ORDER BY role_category, role_code")
        
        return [dict(row) for row in cursor.fetchall()]


def role_get(code: str) -> Optional[dict]:
    """Get role by code."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM project_roles WHERE role_code = ?", (code.upper(),))
        row = cursor.fetchone()
        return dict(row) if row else None


# =============================================================================
# PROJECT TEAM (convenience functions)
# =============================================================================

def get_project_team(project_id: int) -> list[dict]:
    """Get full team for a project with contact details."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM v_project_team WHERE project_id = ?",
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_contact_projects(contact_id: int) -> list[dict]:
    """Get all projects for a contact."""
    return assignment_list(contact_id=contact_id)
