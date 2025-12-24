"""
Projects management tool.

Single tool for all operations: projects, phases, tasks, organizations, norms, exclusions, config, reports.
Supports batch operations for efficient setup.

Schema v2:
- Tasks are linked to phases (not projects). Hierarchy: PROJECT → PHASE → TASK
- Organizations with M:N relationship to projects
- Extended project fields (full_name, country, sector, dates)
"""

from google_calendar.tools.projects.database import (
    ensure_database,
    database_exists,
    # Projects
    project_add, project_get, project_list, project_update, project_delete, project_list_active,
    # Phases
    phase_add, phase_get, phase_list, phase_update, phase_delete,
    # Tasks (v2: linked to phases)
    task_add, task_get, task_list, task_update, task_delete,
    # Norms
    norm_add, norm_get, norm_list, norm_delete,
    # Exclusions
    exclusion_add, exclusion_list, exclusion_delete,
    # Config
    config_get, config_set, config_list,
    # Organizations (v2)
    org_add, org_get, org_list, org_update, org_delete, org_search,
    # Project-Organization links (v2)
    project_org_add, project_org_get, project_org_list, project_org_update, project_org_delete,
    get_project_organizations, get_organization_projects,
)
from google_calendar.db.connection import get_db
from google_calendar.tools.projects.report import generate_report


async def _execute_operation(op: str, p: dict) -> dict:
    """Execute a single operation. All database functions are async."""

    # Projects
    if op == "project_add":
        return await project_add(
            code=p["code"],
            description=p["description"],
            is_billable=p.get("is_billable", False),
            is_active=p.get("is_active", True),
            structure_level=p.get("structure_level", 1),
            full_name=p.get("full_name"),
            country=p.get("country"),
            sector=p.get("sector"),
            start_date=p.get("start_date"),
            end_date=p.get("end_date"),
            contract_value=p.get("contract_value"),
            currency=p.get("currency", "EUR"),
            context=p.get("context"),
        )
    elif op == "project_get":
        return await project_get(id=p.get("id"), code=p.get("code"))
    elif op == "project_list":
        projects = await project_list(
            billable_only=p.get("billable_only", False),
            active_only=p.get("active_only", False)
        )
        return {"projects": projects}
    elif op == "project_list_active":
        projects = await project_list_active()
        return {"projects": projects}
    elif op == "project_update":
        return await project_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"})
    elif op == "project_delete":
        deleted = await project_delete(id=p["id"])
        return {"deleted": deleted}
    elif op == "project_activate":
        return await project_update(id=p["id"], is_active=True)
    elif op == "project_deactivate":
        return await project_update(id=p["id"], is_active=False)

    # Phases
    elif op == "phase_add":
        return await phase_add(
            project_id=p["project_id"],
            code=p["code"],
            description=p.get("description")
        )
    elif op == "phase_get":
        return await phase_get(id=p.get("id"), project_id=p.get("project_id"), code=p.get("code"))
    elif op == "phase_list":
        phases = await phase_list(project_id=p.get("project_id"))
        return {"phases": phases}
    elif op == "phase_update":
        return await phase_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"})
    elif op == "phase_delete":
        deleted = await phase_delete(id=p["id"])
        return {"deleted": deleted}

    # Tasks (linked to phases or universal for project)
    elif op == "task_add":
        return await task_add(
            code=p["code"],
            description=p.get("description"),
            phase_id=p.get("phase_id"),
            project_id=p.get("project_id")
        )
    elif op == "task_get":
        return await task_get(
            id=p.get("id"),
            phase_id=p.get("phase_id"),
            project_id=p.get("project_id"),
            code=p.get("code")
        )
    elif op == "task_list":
        tasks = await task_list(
            phase_id=p.get("phase_id"),
            project_id=p.get("project_id"),
            include_universal=p.get("include_universal", True)
        )
        return {"tasks": tasks}
    elif op == "task_update":
        return await task_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"})
    elif op == "task_delete":
        deleted = await task_delete(id=p["id"])
        return {"deleted": deleted}

    # Organizations (v2)
    elif op == "org_add":
        return await org_add(
            name=p["name"],
            short_name=p.get("short_name"),
            name_local=p.get("name_local"),
            organization_type=p.get("organization_type"),
            parent_org_id=p.get("parent_org_id"),
            country=p.get("country"),
            city=p.get("city"),
            website=p.get("website"),
            context=p.get("context"),
            relationship_status=p.get("relationship_status", "active"),
            first_contact_date=p.get("first_contact_date"),
            notes=p.get("notes"),
        )
    elif op == "org_get":
        return await org_get(id=p.get("id"), name=p.get("name"))
    elif op == "org_list":
        orgs = await org_list(
            organization_type=p.get("organization_type"),
            country=p.get("country"),
            relationship_status=p.get("relationship_status"),
            active_only=p.get("active_only", True),
        )
        return {"organizations": orgs}
    elif op == "org_update":
        return await org_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"})
    elif op == "org_delete":
        deleted = await org_delete(id=p["id"])
        return {"deleted": deleted}
    elif op == "org_search":
        orgs = await org_search(query=p["query"], limit=p.get("limit", 20))
        return {"organizations": orgs}

    # Project-Organization links (v2)
    elif op == "project_org_add":
        return await project_org_add(
            project_id=p["project_id"],
            organization_id=p["organization_id"],
            org_role=p["org_role"],
            contract_value=p.get("contract_value"),
            currency=p.get("currency", "EUR"),
            is_lead=p.get("is_lead", False),
            start_date=p.get("start_date"),
            end_date=p.get("end_date"),
            notes=p.get("notes"),
        )
    elif op == "project_org_get":
        return await project_org_get(id=p["id"])
    elif op == "project_org_list":
        links = await project_org_list(
            project_id=p.get("project_id"),
            organization_id=p.get("organization_id"),
            org_role=p.get("org_role"),
        )
        return {"links": links}
    elif op == "project_org_update":
        return await project_org_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"})
    elif op == "project_org_delete":
        deleted = await project_org_delete(id=p["id"])
        return {"deleted": deleted}
    elif op == "project_orgs":
        orgs = await get_project_organizations(project_id=p["project_id"])
        return {"organizations": orgs}
    elif op == "org_projects":
        projects = await get_organization_projects(organization_id=p["organization_id"])
        return {"projects": projects}

    # Norms
    elif op == "norm_add":
        return await norm_add(year=p["year"], month=p["month"], hours=p["hours"])
    elif op == "norm_get":
        return await norm_get(id=p.get("id"), year=p.get("year"), month=p.get("month"))
    elif op == "norm_list":
        norms = await norm_list(year=p.get("year"))
        return {"norms": norms}
    elif op == "norm_delete":
        deleted = await norm_delete(id=p["id"])
        return {"deleted": deleted}

    # Exclusions
    elif op == "exclusion_add":
        return await exclusion_add(pattern=p["pattern"])
    elif op == "exclusion_list":
        exclusions = await exclusion_list()
        return {"exclusions": exclusions}
    elif op == "exclusion_delete":
        deleted = await exclusion_delete(id=p["id"])
        return {"deleted": deleted}

    # Config
    elif op == "config_get":
        value = await config_get(p["key"])
        return {"key": p["key"], "value": value}
    elif op == "config_set":
        return await config_set(key=p["key"], value=str(p["value"]))
    elif op == "config_list":
        settings = await config_list()
        return {"settings": settings}

    # Roles (project_roles table)
    elif op == "role_add":
        async with get_db() as conn:
            row = await conn.fetchrow(
                """INSERT INTO project_roles (role_code, role_name_en, role_name_ru, role_category, description)
                   VALUES ($1, $2, $3, $4, $5) RETURNING *""",
                p["role_code"].upper(), p["role_name_en"], p.get("role_name_ru"),
                p.get("role_category"), p.get("description")
            )
            return dict(row)
    elif op == "role_get":
        async with get_db() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM project_roles WHERE role_code = $1", p["role_code"].upper()
            )
            return dict(row) if row else None
    elif op == "role_list":
        async with get_db() as conn:
            if p.get("role_category"):
                rows = await conn.fetch(
                    "SELECT * FROM project_roles WHERE role_category = $1 ORDER BY role_code",
                    p["role_category"]
                )
            else:
                rows = await conn.fetch("SELECT * FROM project_roles ORDER BY role_category, role_code")
            return {"roles": [dict(r) for r in rows]}
    elif op == "role_update":
        allowed = {"role_name_en", "role_name_ru", "role_category", "description"}
        updates = {k: v for k, v in p.items() if k in allowed and v is not None}
        if not updates:
            return await _execute_operation("role_get", p)
        set_parts = [f"{k} = ${i+1}" for i, k in enumerate(updates.keys())]
        values = list(updates.values()) + [p["role_code"].upper()]
        async with get_db() as conn:
            await conn.execute(
                f"UPDATE project_roles SET {', '.join(set_parts)} WHERE role_code = ${len(values)}",
                *values
            )
            row = await conn.fetchrow("SELECT * FROM project_roles WHERE role_code = $1", p["role_code"].upper())
            return dict(row) if row else None
    elif op == "role_delete":
        async with get_db() as conn:
            result = await conn.execute("DELETE FROM project_roles WHERE role_code = $1", p["role_code"].upper())
            return {"deleted": result != "DELETE 0"}

    # Reports
    elif op == "report_status":
        return await generate_report(report_type="status", account=p.get("account"))
    elif op == "report_week":
        return await generate_report(
            report_type="week",
            account=p.get("account"),
            export_file=p.get("export_file", False)
        )
    elif op == "report_month":
        return await generate_report(
            report_type="month",
            account=p.get("account"),
            export_file=p.get("export_file", False)
        )
    elif op == "report_custom":
        return await generate_report(
            report_type="custom",
            start_date=p.get("start_date"),
            end_date=p.get("end_date"),
            account=p.get("account"),
            export_file=p.get("export_file", False)
        )

    # Export cleanup (TTL = 1 hour)
    elif op == "cleanup_exports":
        from pathlib import Path

        async with get_db() as conn:
            rows = await conn.fetch(
                """
                SELECT id, file_path FROM export_files
                WHERE expires_at < NOW() AND NOT is_deleted
                """
            )

            deleted = 0
            for row in rows:
                Path(row["file_path"]).unlink(missing_ok=True)
                await conn.execute(
                    "UPDATE export_files SET is_deleted = TRUE WHERE id = $1",
                    row["id"]
                )
                deleted += 1

            return {"deleted": deleted, "message": f"Cleaned up {deleted} expired export files"}

    # Init (schema managed by workflow, this is just a check)
    elif op == "init":
        exists = await database_exists()
        if exists:
            return {"status": "ready", "message": "Database tables exist (schema managed by workflow)"}
        else:
            return {"status": "error", "message": "Database tables do not exist. Check workflow deployment."}

    else:
        raise ValueError(f"Unknown operation: {op}")


async def projects(operations: list[dict]) -> dict:
    """Projects, phases, tasks, and organizations management.

    SKILL REQUIRED: Read projects-management skill for full operations.
    Read calendar-manager skill for event formatting by project structure.

    CRITICAL FOR CALENDAR EVENTS:
        project_list_active: Returns active projects with structure_level, phases, tasks
            → structure_level determines event summary format:
               Level 1: PROJECT * Description
               Level 2: PROJECT * PHASE * Description
               Level 3: PROJECT * PHASE * TASK * Description
            → ALWAYS call before creating work-related calendar events

        projects(operations=[{"op": "project_list_active"}])

    Batch operations via operations=[{op, ...params}].

    TASK HIERARCHY:
        Tasks can be linked in two ways:
        1. Phase-linked: task has phase_id → appears in phase["tasks"]
        2. Universal: task has project_id (phase_id=null) → appears in project["universal_tasks"]

        project_list_active returns:
        {
            "phases": [
                {"code": "A", "tasks": [{"code": "T1", ...}]},  # Phase-linked tasks
                {"code": "B", "tasks": [...]}
            ],
            "universal_tasks": [{"code": "GEN", ...}]  # Universal tasks for all phases
        }

    OPERATION GROUPS:
        Projects: project_add, project_get, project_list, project_list_active, project_update,
                  project_delete, project_activate, project_deactivate
        Phases: phase_add, phase_get, phase_list, phase_update, phase_delete
        Tasks: task_add (phase_id OR project_id), task_get, task_list, task_update, task_delete
        Organizations: org_add, org_get, org_list, org_update, org_delete, org_search
        Project-Org Links: project_org_add/get/list/update/delete, project_orgs, org_projects
        Roles: role_add, role_get, role_list, role_update, role_delete
        Norms: norm_add, norm_get, norm_list, norm_delete
        Reports: report_status, report_week, report_month, report_custom
            → export_file=true: returns download_url for Excel (TTL=1h)
        Export: cleanup_exports - delete expired files
        System: init, config_get, config_set, config_list, exclusion_*

    ROLES (contact role in project):
        role_add: {role_code, role_name_en, role_name_ru?, role_category?, description?}
            role_category: 'consultant', 'client', 'donor', 'partner'
        role_get: {role_code}
        role_list: {role_category?} - filter by category
        role_update: {role_code, role_name_en?, role_name_ru?, role_category?, description?}
        role_delete: {role_code}

    Examples:
        projects(operations=[{"op": "project_list_active"}])
        projects(operations=[{"op": "task_add", "phase_id": 1, "code": "T1"}])  # Phase-linked
        projects(operations=[{"op": "task_add", "project_id": 1, "code": "GEN"}])  # Universal
        projects(operations=[{"op": "role_list"}])  # List all roles
        projects(operations=[{"op": "role_add", "role_code": "SA", "role_name_en": "Senior Advisor"}])
    """
    # Check database exists (async)
    db_exists = await database_exists()
    if not db_exists:
        return {
            "error": "Database not available. Schema should be applied by workflow.",
            "results": [],
            "summary": {"total": len(operations), "success": 0, "errors": len(operations)}
        }

    results = []
    success_count = 0
    error_count = 0

    for i, op_data in enumerate(operations):
        op = op_data.get("op")

        if not op:
            results.append({"index": i, "error": "Missing 'op' field"})
            error_count += 1
            continue

        try:
            result = await _execute_operation(op, op_data)
            results.append({"index": i, "op": op, "result": result})
            success_count += 1
        except ValueError as e:
            results.append({"index": i, "op": op, "error": str(e)})
            error_count += 1
        except Exception as e:
            results.append({"index": i, "op": op, "error": str(e)})
            error_count += 1

    return {
        "results": results,
        "summary": {
            "total": len(operations),
            "success": success_count,
            "errors": error_count
        }
    }
