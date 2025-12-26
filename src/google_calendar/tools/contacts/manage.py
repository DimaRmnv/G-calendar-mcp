"""
Batch management tool for contacts.

Single tool for all CRUD operations: contacts, channels, assignments, roles.
Supports batch operations for efficient setup.
"""

from google_calendar.tools.contacts.database import (
    contacts_tables_exist,
    database_exists,
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
from google_calendar.db.connection import get_db


async def _get_status() -> dict:
    """Get contacts module status."""
    db_exists = await database_exists()
    if not db_exists:
        return {"status": "no_database", "message": "Database connection failed"}

    tables_exist = await contacts_tables_exist()
    if not tables_exist:
        return {"status": "not_initialized", "message": "Tables not found. Check workflow deployment."}

    async with get_db() as conn:
        contacts_count = await conn.fetchval("SELECT COUNT(*) FROM contacts")
        roles_count = await conn.fetchval("SELECT COUNT(*) FROM project_roles")
        assignments_count = await conn.fetchval("SELECT COUNT(*) FROM contact_projects")

    return {
        "status": "ready",
        "contacts": contacts_count,
        "roles": roles_count,
        "assignments": assignments_count
    }


async def _execute_operation(op: str, p: dict) -> dict:
    """Execute a single operation. All database functions are async."""

    # Contacts
    if op == "contact_add":
        return await contact_add(
            first_name=p["first_name"], last_name=p["last_name"],
            organization=p.get("organization"), organization_type=p.get("organization_type"),
            organization_id=p.get("organization_id"), org_notes=p.get("org_notes"),
            job_title=p.get("job_title"), department=p.get("department"),
            country=p.get("country"), city=p.get("city"), timezone=p.get("timezone"),
            preferred_channel=p.get("preferred_channel", "email"),
            preferred_language=p.get("preferred_language", "en"),
            context=p.get("context"),
            relationship_type=p.get("relationship_type"),
            relationship_strength=p.get("relationship_strength"),
            last_interaction_date=p.get("last_interaction_date"),
            notes=p.get("notes")
        )
    elif op == "contact_get":
        return await contact_get(
            id=p.get("id"), email=p.get("email"), telegram=p.get("telegram"), phone=p.get("phone"),
            include_channels=p.get("include_channels", False),
            include_projects=p.get("include_projects", False)
        )
    elif op == "contact_list":
        contacts = await contact_list(
            organization=p.get("organization"), organization_type=p.get("organization_type"),
            country=p.get("country"), project_id=p.get("project_id"),
            role_code=p.get("role_code"), preferred_channel=p.get("preferred_channel"),
            org_type=p.get("org_type"), active_only=p.get("active_only", True)
        )
        return {"contacts": contacts, "total": len(contacts)}
    elif op == "contact_update":
        contact_id = p.get("id") or p.get("contact_id")
        updates = {k: v for k, v in p.items() if k not in ("id", "contact_id", "op")}
        return await contact_update(contact_id, **updates)
    elif op == "contact_delete":
        contact_id = p.get("id") or p.get("contact_id")
        deleted = await contact_delete(id=contact_id)
        return {"deleted": deleted, "id": contact_id}
    elif op == "contact_search":
        contacts = await contact_search(
            p["query"], limit=p.get("limit", 20), threshold=p.get("threshold", 60)
        )
        return {"contacts": contacts}
    elif op == "contact_activate":
        return await contact_update(id=p["id"], is_active=True)
    elif op == "contact_deactivate":
        return await contact_update(id=p["id"], is_active=False)

    # Channels
    elif op == "channel_add":
        return await channel_add(
            contact_id=p["contact_id"], channel_type=p["channel_type"],
            channel_value=p["channel_value"], channel_label=p.get("channel_label"),
            is_primary=p.get("is_primary", False), notes=p.get("notes")
        )
    elif op == "channel_list":
        channels = await channel_list(contact_id=p["contact_id"])
        return {"channels": channels}
    elif op == "channel_get":
        channel_id = p.get("id") or p.get("channel_id")
        return await channel_get(id=channel_id)
    elif op == "channel_update":
        channel_id = p.get("id") or p.get("channel_id")
        updates = {k: v for k, v in p.items() if k not in ("id", "channel_id", "op")}
        return await channel_update(channel_id, **updates)
    elif op == "channel_delete":
        channel_id = p.get("id") or p.get("channel_id")
        deleted = await channel_delete(id=channel_id)
        return {"deleted": deleted, "id": channel_id}
    elif op == "channel_set_primary":
        channel_id = p.get("id") or p.get("channel_id")
        return await channel_set_primary(id=channel_id)

    # Assignments
    elif op == "assignment_add":
        return await assignment_add(
            contact_id=p["contact_id"], project_id=p["project_id"], role_code=p["role_code"],
            start_date=p.get("start_date"), end_date=p.get("end_date"),
            workdays_allocated=p.get("workdays_allocated"), notes=p.get("notes")
        )
    elif op == "assignment_get":
        assignment_id = p.get("id") or p.get("assignment_id")
        return await assignment_get(id=assignment_id)
    elif op == "assignment_list":
        assignments = await assignment_list(
            contact_id=p.get("contact_id"), project_id=p.get("project_id"),
            role_code=p.get("role_code"), active_only=p.get("active_only", True)
        )
        return {"assignments": assignments}
    elif op == "assignment_update":
        assignment_id = p.get("id") or p.get("assignment_id")
        updates = {k: v for k, v in p.items() if k not in ("id", "assignment_id", "op")}
        return await assignment_update(assignment_id, **updates)
    elif op == "assignment_delete":
        assignment_id = p.get("id") or p.get("assignment_id")
        deleted = await assignment_delete(id=assignment_id)
        return {"deleted": deleted, "id": assignment_id}
    elif op == "assignment_activate":
        assignment_id = p.get("id") or p.get("assignment_id")
        return await assignment_update(id=assignment_id, is_active=True)
    elif op == "assignment_deactivate":
        assignment_id = p.get("id") or p.get("assignment_id")
        return await assignment_update(id=assignment_id, is_active=False)

    # Roles
    elif op == "role_list":
        roles = await role_list(category=p.get("category"))
        return {"roles": roles}
    elif op == "role_get":
        return await role_get(code=p["code"])

    # Team views
    elif op == "project_team":
        team = await get_project_team(project_id=p["project_id"])
        return {"team": team}
    elif op == "contact_projects":
        projects = await get_contact_projects(contact_id=p["contact_id"])
        return {"projects": projects}

    # Lookup/resolve operations (these are sync but call async db functions internally)
    elif op == "contact_resolve":
        return await resolve_contact(
            identifier=p["identifier"],
            context=p.get("context")
        )
    elif op == "contact_resolve_multiple":
        return await resolve_multiple(
            identifiers=p["identifiers"],
            context=p.get("context")
        )
    elif op == "contact_preferred_channel":
        return await get_preferred_channel(
            contact=p["contact"],
            channel_type=p.get("channel_type"),
            for_purpose=p.get("for_purpose")
        )

    # Enrichment operations
    elif op == "suggest_enrichment":
        return await suggest_enrichment(
            contact_id=p["contact_id"],
            sources=p.get("sources")
        )
    elif op == "suggest_new_contacts":
        return await suggest_new_contacts(
            sources=p.get("sources"),
            limit=p.get("limit", 20),
            period=p.get("period", "month")
        )
    elif op == "contact_brief":
        return await contact_brief(
            contact_id=p["contact_id"],
            days_back=p.get("days_back", 7),
            days_forward=p.get("days_forward", 7)
        )

    # Reporting operations
    elif op == "report":
        return await contacts_report(
            report_type=p["report_type"],
            project_id=p.get("project_id"),
            organization=p.get("organization"),
            days_stale=p.get("days_stale", 90),
            limit=p.get("limit", 50)
        )
    elif op == "export_contacts":
        return await export_contacts_excel(
            filter_params=p.get("filter_params"),
            output_path=p.get("output_path")
        )
    elif op == "export_project_team":
        return await export_project_team_excel(
            project_id=p["project_id"],
            output_path=p.get("output_path")
        )

    # System operations
    elif op == "init":
        tables_exist = await contacts_tables_exist()
        if tables_exist:
            return {"status": "ready", "message": "Tables exist (schema managed by workflow)"}
        else:
            return {"status": "error", "message": "Tables not found. Check workflow deployment."}
    elif op == "status":
        return await _get_status()

    else:
        raise ValueError(f"Unknown operation: {op}")


async def contacts(operations: list[dict]) -> dict:
    """Unified contacts management.

    SKILL REQUIRED: Read contacts-management skill for database operations.
    For sending messages, read mcp-orchestration skill for channel routing.

    CONTACTS:

        LIST/SEARCH return COMPACT format (id, name, org, job_title, country, channel).
        Use contact_get(id) for FULL details. Add include_channels/include_projects for related data.

        contact_list    : List all (compact). Filters: organization_id, country, org_type,
                          preferred_channel. Returns: CONTACT_COMPACT[]
        contact_search  : Search by name/org/job (compact + email + score). Returns: CONTACT_COMPACT[]
        contact_get     : Full details. Params: id, include_channels (bool), include_projects (bool).
                          Returns: CONTACT_FULL, optionally with channels[] and projects[]
        contact_add     : Create. Requires: first_name, last_name. Returns: CONTACT_COMPACT
        contact_update  : Update. Requires: id. Returns: CONTACT_COMPACT
        contact_delete  : Delete. Requires: id. Returns: {deleted, id}

    QUICK LOOKUP (for messaging):

        contact_resolve          : Find by partial name. Returns: id, display_name, org,
                                   preferred_channel, primary_email, telegram_username
        contact_resolve_multiple : Batch resolve. Returns: array of above

    PROJECT TEAMS:

        project_team    : Team members with roles and contact info (already optimized).
                          Requires: project_id. Returns: team[]

    CHANNELS:

        channel_list    : Contact's communication channels. Requires: contact_id
        channel_add     : Add channel. Requires: contact_id, channel_type, channel_value
        channel_update  : Update. Requires: id
        channel_delete  : Delete. Requires: id. Returns: {deleted, id}
        channel_set_primary : Set as primary. Requires: id

    ASSIGNMENTS (contact ↔ project roles):

        assignment_list   : Contact's project assignments (compact). Requires: contact_id
        assignment_add    : Assign to project. Requires: contact_id, project_id, role_code
        assignment_update : Update. Requires: id
        assignment_delete : Remove. Requires: id. Returns: {deleted, id}

    FIELD SETS:

        CONTACT_COMPACT: id, first_name, last_name, display_name, organization_name,
                         job_title, country, preferred_channel

        CONTACT_FULL: CONTACT_COMPACT + organization_id, org_type, department, city, timezone,
                      preferred_language, context, relationship_type, relationship_strength,
                      last_interaction_date, primary_email, primary_phone, telegram_chat_id,
                      telegram_username, teams_chat_id, notes, created_at, updated_at

        CONTACT_FULL + related: CONTACT_FULL + channels[{type, value, is_primary}]
                                + projects[{project_code, role_code, role_name}]

    USAGE PATTERNS:

        Dropdown/picker        → contact_list or contact_search (compact)
        Contact card           → contact_get(id, include_channels=True, include_projects=True)
        Send message           → contact_resolve("Altynbek") → get preferred_channel + value
        Add to project team    → contact_list → select → assignment_add
        Project stakeholders   → project_team(project_id)
        Update contact info    → contact_get(id) → contact_update(id, ...)

    BATCH OPERATIONS:
        contact_id=-1 means "use ID from previous contact_add in same batch"
        contacts(operations=[
            {"op": "contact_add", "first_name": "John", "last_name": "Doe"},
            {"op": "channel_add", "contact_id": -1, "channel_type": "email", "channel_value": "john@wb.org"},
            {"op": "assignment_add", "contact_id": -1, "project_id": 5, "role_code": "DPM"}
        ])

    Examples:
        contacts(operations=[{"op": "contact_list", "country": "Uzbekistan"}])
        contacts(operations=[{"op": "contact_search", "query": "ADB"}])
        contacts(operations=[{"op": "contact_get", "id": 27, "include_channels": true}])
        contacts(operations=[{"op": "contact_resolve", "identifier": "Altynbek"}])
        contacts(operations=[{"op": "project_team", "project_id": 1}])
    """
    # Check database for non-system operations
    first_op = operations[0].get("op") if operations else None
    if first_op not in ("init", "status"):
        tables_exist = await contacts_tables_exist()
        if not tables_exist:
            return {
                "error": "Database tables not available. Schema should be applied by workflow.",
                "results": [],
                "summary": {"total": len(operations), "success": 0, "errors": len(operations)}
            }

    results = []
    success_count = 0
    error_count = 0
    last_contact_id = None  # For contact_id=-1 in batch operations

    for i, op_data in enumerate(operations):
        op = op_data.get("op")

        if not op:
            results.append({"index": i, "error": "Missing 'op' field"})
            error_count += 1
            continue

        # Replace contact_id=-1 with last created contact ID
        if op_data.get("contact_id") == -1:
            if last_contact_id is None:
                results.append({"index": i, "op": op, "error": "contact_id=-1 but no contact_add before"})
                error_count += 1
                continue
            op_data = {**op_data, "contact_id": last_contact_id}

        try:
            result = await _execute_operation(op, op_data)
            results.append({"index": i, "op": op, "result": result})
            success_count += 1

            # Track last created contact for contact_id=-1
            if op == "contact_add" and result.get("id"):
                last_contact_id = result["id"]
        except ValueError as e:
            results.append({"index": i, "op": op, "error": str(e)})
            error_count += 1
        except Exception as e:
            results.append({"index": i, "op": op, "error": str(e)})
            error_count += 1

    return {
        "results": results,
        "summary": {"total": len(operations), "success": success_count, "errors": error_count}
    }
