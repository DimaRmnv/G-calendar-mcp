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
from google_calendar.tools.contacts.lookup import (
    resolve_contact,
    resolve_multiple,
    get_preferred_channel,
    suggest_enrichment,
    suggest_new_contacts,
    contact_brief,
)
from google_calendar.tools.contacts.report import (
    contacts_report,
    export_contacts_excel,
    export_project_team_excel,
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
        organization_id=p.get("organization_id"),  # v2: FK to organizations table
        job_title=p.get("job_title"), department=p.get("department"),
        country=p.get("country"), city=p.get("city"), timezone=p.get("timezone"),
        preferred_channel=p.get("preferred_channel", "email"),
        preferred_language=p.get("preferred_language", "en"),
        # v2 relationship tracking
        context=p.get("context"),
        relationship_type=p.get("relationship_type"),
        relationship_strength=p.get("relationship_strength"),
        last_interaction_date=p.get("last_interaction_date"),
        notes=p.get("notes")
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
    "contact_search": lambda p: {"contacts": contact_search(
        p["query"], limit=p.get("limit", 20), threshold=p.get("threshold", 60)
    )},
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

    # Lookup/resolve operations
    "contact_resolve": lambda p: resolve_contact(
        identifier=p["identifier"],
        context=p.get("context")
    ),
    "contact_resolve_multiple": lambda p: resolve_multiple(
        identifiers=p["identifiers"],
        context=p.get("context")
    ),
    "contact_preferred_channel": lambda p: get_preferred_channel(
        contact=p["contact"],
        channel_type=p.get("channel_type"),
        for_purpose=p.get("for_purpose")
    ),

    # Enrichment operations
    "suggest_enrichment": lambda p: suggest_enrichment(
        contact_id=p["contact_id"],
        sources=p.get("sources")
    ),
    "suggest_new_contacts": lambda p: suggest_new_contacts(
        sources=p.get("sources"),
        limit=p.get("limit", 20),
        period=p.get("period", "month")
    ),
    "contact_brief": lambda p: contact_brief(
        contact_id=p["contact_id"],
        days_back=p.get("days_back", 7),
        days_forward=p.get("days_forward", 7)
    ),

    # Reporting operations
    "report": lambda p: contacts_report(
        report_type=p["report_type"],
        project_id=p.get("project_id"),
        organization=p.get("organization"),
        days_stale=p.get("days_stale", 90),
        limit=p.get("limit", 50)
    ),
    "export_contacts": lambda p: export_contacts_excel(
        filter_params=p.get("filter_params"),
        output_path=p.get("output_path")
    ),
    "export_project_team": lambda p: export_project_team_excel(
        project_id=p["project_id"],
        output_path=p.get("output_path")
    ),

    "init": lambda p: _init_contacts(force_reset=p.get("force_reset", False)),
    "status": lambda p: _get_status(),
}


async def contacts(operations: list[dict]) -> dict:
    """Unified contacts management.

    SKILL REQUIRED: Read contacts-management skill for database operations.
    For sending messages, read mcp-orchestration skill for channel routing.

    KEY OPERATIONS FOR CALENDAR/COMMUNICATION:

        project_team: Get all contacts for a project with roles and emails
            → Use for meeting attendees, team notifications
            contacts(operations=[{"op": "project_team", "project_id": 5}])

        contact_resolve: Find contact by partial name
            → Returns email, preferred_channel, organization
            contacts(operations=[{"op": "contact_resolve", "identifier": "Altynbek"}])

        contact_resolve_multiple: Batch resolve
            contacts(operations=[{"op": "contact_resolve_multiple", "identifiers": ["Michael", "Elena"]}])

    Batch operations via operations=[{op, ...params}].

    OPERATION GROUPS:
        Contacts: contact_add, contact_get, contact_list, contact_update, contact_delete, contact_search
        Channels: channel_add, channel_list, channel_update, channel_delete, channel_set_primary
        Assignments: assignment_add, assignment_list, assignment_update, assignment_delete
        Lookup: contact_resolve, contact_resolve_multiple, contact_preferred_channel, project_team
        Enrichment: suggest_enrichment, suggest_new_contacts, contact_brief
        Reporting: report, export_contacts, export_project_team
        System: init, status, role_list, role_get

    Examples:
        contacts(operations=[{"op": "project_team", "project_id": 5}])
        contacts(operations=[{"op": "contact_resolve", "identifier": "Altynbek"}])
        contacts(operations=[{"op": "contact_add", "first_name": "John", "last_name": "Doe", "organization": "ADB"}])
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
