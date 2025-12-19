"""
Batch management tool for contacts.

Single tool for all CRUD operations: contacts, channels, assignments, roles.
Supports batch operations for efficient setup.
"""

from google_calendar.tools.contacts.database import (
    ensure_contacts_schema,
    init_contacts_schema,
    contacts_tables_exist,
    contact_add, contact_get, contact_list, contact_update, contact_delete, contact_search,
    channel_add, channel_list, channel_get, channel_update, channel_delete, channel_set_primary,
    assignment_add, assignment_get, assignment_list, assignment_update, assignment_delete,
    role_list, role_get,
    get_project_team, get_contact_projects,
)


def _init_contacts(force_reset: bool = False) -> dict:
    """Initialize contacts tables."""
    if contacts_tables_exist() and not force_reset:
        return {
            "status": "exists",
            "message": "Contacts tables already exist. Use force_reset=True to recreate."
        }
    
    if force_reset and contacts_tables_exist():
        from google_calendar.tools.contacts.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP VIEW IF EXISTS v_contacts_full")
            cursor.execute("DROP VIEW IF EXISTS v_project_team")
            cursor.execute("DROP VIEW IF EXISTS v_contact_projects")
            cursor.execute("DROP TABLE IF EXISTS contact_projects")
            cursor.execute("DROP TABLE IF EXISTS contact_channels")
            cursor.execute("DROP TABLE IF EXISTS contacts")
            cursor.execute("DROP TABLE IF EXISTS project_roles")
    
    init_contacts_schema()
    return {"status": "created", "message": "Contacts tables created with 19 standard roles."}


def _get_status() -> dict:
    """Get contacts module status."""
    from google_calendar.tools.contacts.database import get_connection, database_exists
    
    if not database_exists():
        return {"status": "no_database", "message": "Database does not exist"}
    
    if not contacts_tables_exist():
        return {"status": "not_initialized", "message": "Run init first."}
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM contacts")
        contacts_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM project_roles")
        roles_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM contact_projects")
        assignments_count = cursor.fetchone()["cnt"]
    
    return {
        "status": "ready",
        "contacts": contacts_count,
        "roles": roles_count,
        "assignments": assignments_count
    }


OPERATIONS = {
    "contact_add": lambda p: contact_add(
        first_name=p["first_name"], last_name=p["last_name"],
        organization=p.get("organization"), organization_type=p.get("organization_type"),
        job_title=p.get("job_title"), department=p.get("department"),
        country=p.get("country"), city=p.get("city"), timezone=p.get("timezone"),
        preferred_channel=p.get("preferred_channel", "email"),
        preferred_language=p.get("preferred_language", "en"), notes=p.get("notes")
    ),
    "contact_get": lambda p: contact_get(
        id=p.get("id"), email=p.get("email"), telegram=p.get("telegram"), phone=p.get("phone")
    ),
    "contact_list": lambda p: {"contacts": contact_list(
        organization=p.get("organization"), organization_type=p.get("organization_type"),
        country=p.get("country"), project_id=p.get("project_id"),
        role_code=p.get("role_code"), active_only=p.get("active_only", True)
    )},
    "contact_update": lambda p: contact_update(p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "contact_delete": lambda p: {"deleted": contact_delete(id=p["id"])},
    "contact_search": lambda p: {"contacts": contact_search(p["query"], p.get("limit", 20))},
    "contact_activate": lambda p: contact_update(id=p["id"], is_active=True),
    "contact_deactivate": lambda p: contact_update(id=p["id"], is_active=False),

    "channel_add": lambda p: channel_add(
        contact_id=p["contact_id"], channel_type=p["channel_type"],
        channel_value=p["channel_value"], channel_label=p.get("channel_label"),
        is_primary=p.get("is_primary", False), notes=p.get("notes")
    ),
    "channel_list": lambda p: {"channels": channel_list(contact_id=p["contact_id"])},
    "channel_get": lambda p: channel_get(id=p["id"]),
    "channel_update": lambda p: channel_update(p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "channel_delete": lambda p: {"deleted": channel_delete(id=p["id"])},
    "channel_set_primary": lambda p: channel_set_primary(id=p["id"]),

    "assignment_add": lambda p: assignment_add(
        contact_id=p["contact_id"], project_id=p["project_id"], role_code=p["role_code"],
        start_date=p.get("start_date"), end_date=p.get("end_date"),
        workdays_allocated=p.get("workdays_allocated"), notes=p.get("notes")
    ),
    "assignment_get": lambda p: assignment_get(id=p["id"]),
    "assignment_list": lambda p: {"assignments": assignment_list(
        contact_id=p.get("contact_id"), project_id=p.get("project_id"),
        role_code=p.get("role_code"), active_only=p.get("active_only", True)
    )},
    "assignment_update": lambda p: assignment_update(p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "assignment_delete": lambda p: {"deleted": assignment_delete(id=p["id"])},
    "assignment_activate": lambda p: assignment_update(id=p["id"], is_active=True),
    "assignment_deactivate": lambda p: assignment_update(id=p["id"], is_active=False),

    "role_list": lambda p: {"roles": role_list(category=p.get("category"))},
    "role_get": lambda p: role_get(code=p["code"]),

    "project_team": lambda p: {"team": get_project_team(project_id=p["project_id"])},
    "contact_projects": lambda p: {"projects": get_contact_projects(contact_id=p["contact_id"])},

    "init": lambda p: _init_contacts(force_reset=p.get("force_reset", False)),
    "status": lambda p: _get_status(),
}


async def contacts(operations: list[dict]) -> dict:
    """
    Unified contacts management tool.

    Args:
        operations: List of operations. Each dict has 'op' + params.

    Operations:
        Contacts:
            contact_add: first_name, last_name, organization?, organization_type?, 
                        job_title?, country?, preferred_channel?, notes?
            contact_get: id OR email OR telegram OR phone
            contact_list: organization?, country?, project_id?, active_only?
            contact_update: id + fields to update
            contact_delete: id
            contact_search: query, limit?

        Channels:
            channel_add: contact_id, channel_type, channel_value, is_primary?
            channel_list: contact_id
            channel_update: id + fields
            channel_delete: id
            channel_set_primary: id

        Assignments:
            assignment_add: contact_id, project_id, role_code, start_date?, workdays_allocated?
            assignment_list: contact_id?, project_id?, role_code?
            assignment_update: id + fields
            assignment_delete: id

        Roles: role_list, role_get
        Views: project_team, contact_projects
        System: init, status

    Valid values:
        organization_type: donor, client, partner, bfc, government, bank, mfi, other
        preferred_channel: email, telegram, teams, phone, whatsapp
        channel_type: email, phone, telegram_id, telegram_username, telegram_chat_id,
                     teams_id, teams_chat_id, whatsapp, linkedin, skype
        role_category: consultant, client, donor, partner

    Example:
        contacts(operations=[
            {"op": "init"},
            {"op": "contact_add", "first_name": "Altynbek", "last_name": "Sydykov",
             "organization": "Aiyl Bank", "country": "Kyrgyzstan"},
            {"op": "channel_add", "contact_id": 1, "channel_type": "email",
             "channel_value": "a.sydykov@aiylbank.kg", "is_primary": True},
            {"op": "assignment_add", "contact_id": 1, "project_id": 5, "role_code": "CPM"}
        ])
    """
    first_op = operations[0].get("op") if operations else None
    if first_op not in ("init", "status"):
        try:
            ensure_contacts_schema()
        except RuntimeError as e:
            return {"error": str(e), "hint": "Run init first or enable time_tracking."}

    results = []
    success_count = 0
    error_count = 0

    for i, op_data in enumerate(operations):
        op = op_data.get("op")
        if not op:
            results.append({"index": i, "error": "Missing 'op' field"})
            error_count += 1
            continue
        if op not in OPERATIONS:
            results.append({"index": i, "op": op, "error": f"Unknown operation: {op}"})
            error_count += 1
            continue
        try:
            result = OPERATIONS[op](op_data)
            results.append({"index": i, "op": op, "result": result})
            success_count += 1
        except Exception as e:
            results.append({"index": i, "op": op, "error": str(e)})
            error_count += 1

    return {
        "results": results,
        "summary": {"total": len(operations), "success": success_count, "errors": error_count}
    }
