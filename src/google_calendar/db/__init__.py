"""Database module for Google Calendar MCP.

Supports both SQLite (local mode) and PostgreSQL (cloud mode).
All data stored in single database: google_calendar_mcp

Tables:
- Time tracking: projects, phases, tasks, norms, exclusions, settings
- Contacts: contacts, contact_channels, project_roles, contact_projects
"""

from google_calendar.db.connection import (
    DatabaseManager,
    get_db,
    get_db_url,
    get_pool,
    create_pool,
    close_pool,
    init_db,
    ensure_db_initialized,
    is_postgres_configured,
    ASYNCPG_AVAILABLE,
)

__all__ = [
    "DatabaseManager",
    "get_db",
    "get_db_url",
    "get_pool",
    "create_pool",
    "close_pool",
    "init_db",
    "ensure_db_initialized",
    "is_postgres_configured",
    "ASYNCPG_AVAILABLE",
]
