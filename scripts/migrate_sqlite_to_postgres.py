#!/usr/bin/env python3
"""
Migrate data from SQLite (local) to PostgreSQL (cloud).

Reads from ~/.mcp/google-calendar/time_tracking.db and outputs PostgreSQL SQL.

Usage:
    python scripts/migrate_sqlite_to_postgres.py > gc_data.sql
    scp gc_data.sql root@157.173.109.132:~/apps/google-calendar-mcp/
    ssh root@157.173.109.132 "docker exec -i travel-postgres psql -U travel -d google_calendar_mcp < ~/apps/google-calendar-mcp/gc_data.sql"
"""

import sqlite3
import sys
from pathlib import Path
from typing import Any


def escape_string(value: Any, is_boolean: bool = False) -> str:
    """Escape string for PostgreSQL."""
    if value is None:
        return "NULL"
    if is_boolean or isinstance(value, bool):
        # Handle SQLite integer booleans (1/0) and Python bools
        if value in (1, True, "1", "true", "True"):
            return "TRUE"
        elif value in (0, False, "0", "false", "False"):
            return "FALSE"
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    # Escape single quotes
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


BOOLEAN_COLUMNS = {
    "projects": {"is_billable", "is_active"},
    "contacts": {"is_active"},
    "contact_channels": {"is_primary"},
    "contact_projects": {"is_active"},
}


GENERATED_COLUMNS = {
    "contacts": {"display_name"},
}


def migrate_table(
    conn: sqlite3.Connection,
    table_name: str,
    columns: list[str],
    has_serial_id: bool = True
) -> list[str]:
    """Generate INSERT statements for a table."""
    statements = []
    cursor = conn.cursor()

    # Get boolean columns for this table
    bool_cols = BOOLEAN_COLUMNS.get(table_name, set())
    # Get generated columns to exclude
    gen_cols = GENERATED_COLUMNS.get(table_name, set())

    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        if not rows:
            statements.append(f"-- No data in {table_name}")
            return statements

        # Get column names from cursor description, excluding generated columns
        all_col_names = [desc[0] for desc in cursor.description]
        col_indices = [(i, name) for i, name in enumerate(all_col_names) if name not in gen_cols]
        col_names = [name for _, name in col_indices]

        statements.append(f"-- {table_name}: {len(rows)} rows")

        for row in rows:
            values = []
            for idx, col_name in col_indices:
                val = row[idx]
                is_bool = col_name in bool_cols
                values.append(escape_string(val, is_boolean=is_bool))

            cols_str = ", ".join(col_names)
            vals_str = ", ".join(values)
            statements.append(f"INSERT INTO {table_name} ({cols_str}) VALUES ({vals_str});")

        # Reset sequence if table has SERIAL id
        if has_serial_id:
            cursor.execute(f"SELECT MAX(id) FROM {table_name}")
            max_id = cursor.fetchone()[0]
            if max_id:
                statements.append(
                    f"SELECT setval('{table_name}_id_seq', {max_id}, true);"
                )

    except sqlite3.OperationalError as e:
        statements.append(f"-- Table {table_name} not found: {e}")

    return statements


def main():
    # Find SQLite database
    db_path = Path.home() / ".mcp" / "google-calendar" / "time_tracking.db"

    if not db_path.exists():
        print(f"-- SQLite database not found: {db_path}", file=sys.stderr)
        print("-- No data to migrate")
        sys.exit(0)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("-- Google Calendar MCP Data Migration")
    print("-- SQLite to PostgreSQL")
    print(f"-- Source: {db_path}")
    print()
    print("BEGIN;")
    print()

    # Truncate all tables first (in reverse dependency order)
    print("-- Truncate existing data")
    print("TRUNCATE TABLE contact_projects CASCADE;")
    print("TRUNCATE TABLE contact_channels CASCADE;")
    print("TRUNCATE TABLE contacts CASCADE;")
    print("TRUNCATE TABLE settings CASCADE;")
    print("TRUNCATE TABLE exclusions CASCADE;")
    print("TRUNCATE TABLE norms CASCADE;")
    print("TRUNCATE TABLE tasks CASCADE;")
    print("TRUNCATE TABLE phases CASCADE;")
    print("TRUNCATE TABLE projects CASCADE;")
    print()

    # Migrate time_tracking tables
    print("-- =============================================================================")
    print("-- TIME TRACKING TABLES")
    print("-- =============================================================================")
    print()

    # Projects
    for stmt in migrate_table(conn, "projects", [
        "id", "code", "description", "is_billable", "is_active",
        "position", "structure_level", "created_at", "updated_at"
    ]):
        print(stmt)
    print()

    # Phases
    for stmt in migrate_table(conn, "phases", [
        "id", "project_id", "code", "description", "created_at"
    ]):
        print(stmt)
    print()

    # Tasks
    for stmt in migrate_table(conn, "tasks", [
        "id", "project_id", "code", "description", "created_at"
    ]):
        print(stmt)
    print()

    # Norms
    for stmt in migrate_table(conn, "norms", [
        "id", "year", "month", "hours"
    ]):
        print(stmt)
    print()

    # Exclusions
    for stmt in migrate_table(conn, "exclusions", [
        "id", "pattern", "created_at"
    ]):
        print(stmt)
    print()

    # Settings (no serial id - key is primary key)
    for stmt in migrate_table(conn, "settings", [
        "key", "value", "updated_at"
    ], has_serial_id=False):
        print(stmt)
    print()

    # Migrate contacts tables
    print("-- =============================================================================")
    print("-- CONTACTS TABLES")
    print("-- =============================================================================")
    print()

    # Contacts - handle old vs new schema
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM contacts LIMIT 0")
        col_names = [desc[0] for desc in cursor.description]

        # Check if old schema (has 'name' column) or new schema (has 'first_name')
        if 'name' in col_names and 'first_name' not in col_names:
            # Old schema - need to transform
            print("-- Note: Migrating from old contacts schema (name -> first_name/last_name)")
            cursor.execute("SELECT * FROM contacts")
            rows = cursor.fetchall()
            if rows:
                print(f"-- contacts: {len(rows)} rows (transformed)")
                for row in rows:
                    row_dict = dict(zip(col_names, row))
                    # Split name into first_name and last_name
                    full_name = row_dict.get('name', '')
                    parts = full_name.split(' ', 1) if full_name else ['', '']
                    first_name = parts[0] if parts else ''
                    last_name = parts[1] if len(parts) > 1 else ''

                    values = [
                        escape_string(row_dict.get('id')),
                        escape_string(first_name),
                        escape_string(last_name),
                        escape_string(row_dict.get('company')),  # -> organization
                        escape_string(row_dict.get('position')),  # -> job_title
                        escape_string(row_dict.get('notes')),
                        escape_string(row_dict.get('is_active', True), is_boolean=True),
                        escape_string(row_dict.get('created_at')),
                        escape_string(row_dict.get('updated_at'))
                    ]

                    print(f"INSERT INTO contacts (id, first_name, last_name, organization, job_title, notes, is_active, created_at, updated_at) VALUES ({', '.join(values)});")

                cursor.execute("SELECT MAX(id) FROM contacts")
                max_id = cursor.fetchone()[0]
                if max_id:
                    print(f"SELECT setval('contacts_id_seq', {max_id}, true);")
        else:
            # New schema - direct migration
            for stmt in migrate_table(conn, "contacts", [
                "id", "first_name", "last_name", "organization", "organization_type",
                "job_title", "department", "country", "city", "timezone",
                "preferred_channel", "preferred_language", "notes",
                "created_at", "updated_at", "is_active"
            ]):
                print(stmt)
    except sqlite3.OperationalError as e:
        print(f"-- Table contacts not found: {e}")
    print()

    # Contact channels - handle schema differences
    try:
        cursor.execute("SELECT * FROM contact_channels LIMIT 0")
        col_names = [desc[0] for desc in cursor.description]

        # Map old columns to new
        if 'label' in col_names and 'channel_label' not in col_names:
            # Rename label -> channel_label
            print("-- Note: Migrating contact_channels with label -> channel_label")
            cursor.execute("SELECT * FROM contact_channels")
            rows = cursor.fetchall()
            if rows:
                print(f"-- contact_channels: {len(rows)} rows")
                for row in rows:
                    row_dict = dict(zip(col_names, row))
                    values = [
                        escape_string(row_dict.get('id')),
                        escape_string(row_dict.get('contact_id')),
                        escape_string(row_dict.get('channel_type')),
                        escape_string(row_dict.get('channel_value')),
                        escape_string(row_dict.get('label')),  # -> channel_label
                        escape_string(row_dict.get('is_primary', False), is_boolean=True),
                        "NULL"  # notes
                    ]
                    print(f"INSERT INTO contact_channels (id, contact_id, channel_type, channel_value, channel_label, is_primary, notes) VALUES ({', '.join(values)});")

                cursor.execute("SELECT MAX(id) FROM contact_channels")
                max_id = cursor.fetchone()[0]
                if max_id:
                    print(f"SELECT setval('contact_channels_id_seq', {max_id}, true);")
        else:
            for stmt in migrate_table(conn, "contact_channels", [
                "id", "contact_id", "channel_type", "channel_value",
                "channel_label", "is_primary", "notes"
            ]):
                print(stmt)
    except sqlite3.OperationalError as e:
        print(f"-- Table contact_channels not found: {e}")
    print()

    # Project roles - skip, use defaults from schema.sql
    print("-- project_roles: Skipped (use defaults from schema.sql)")
    print()

    # Contact projects - handle schema differences
    try:
        cursor.execute("SELECT * FROM contact_projects LIMIT 0")
        col_names = [desc[0] for desc in cursor.description]

        if 'role_id' in col_names and 'role_code' not in col_names:
            # Old schema with role_id instead of role_code
            print("-- Note: contact_projects has old schema (role_id) - manual migration may be needed")
            print("-- Skipping contact_projects automatic migration")
        else:
            for stmt in migrate_table(conn, "contact_projects", [
                "id", "contact_id", "project_id", "role_code",
                "start_date", "end_date", "is_active", "workdays_allocated", "notes"
            ]):
                print(stmt)
    except sqlite3.OperationalError as e:
        print(f"-- Table contact_projects not found: {e}")
    print()

    print("COMMIT;")
    print()
    print("-- Migration complete")

    conn.close()


if __name__ == "__main__":
    main()
