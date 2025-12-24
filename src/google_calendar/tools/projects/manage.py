"""
Projects management tool.

Single tool for all operations: projects, phases, tasks, organizations, norms, exclusions, config, reports.
Supports batch operations for efficient setup.

Schema v2:
- Tasks are linked to phases (not projects). Hierarchy: PROJECT → PHASE → TASK
- Organizations with M:N relationship to projects
- Extended project fields (full_name, country, sector, dates)
"""

from typing import Optional
from google_calendar.tools.projects.database import (
    ensure_database,
    init_database,
    database_exists,
    get_database_path,
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
from google_calendar.tools.projects.report import generate_report


# Operation handlers
OPERATIONS = {
    # Projects (v2: extended with full_name, country, sector, dates)
    "project_add": lambda p: project_add(
        code=p["code"],
        description=p["description"],
        is_billable=p.get("is_billable", False),
        is_active=p.get("is_active", True),
        position=p.get("position"),
        structure_level=p.get("structure_level", 1),
        full_name=p.get("full_name"),
        country=p.get("country"),
        sector=p.get("sector"),
        start_date=p.get("start_date"),
        end_date=p.get("end_date"),
        contract_value=p.get("contract_value"),
        currency=p.get("currency", "EUR"),
        context=p.get("context"),
    ),
    "project_get": lambda p: project_get(id=p.get("id"), code=p.get("code")),
    "project_list": lambda p: {"projects": project_list(
        billable_only=p.get("billable_only", False),
        active_only=p.get("active_only", False)
    )},
    "project_list_active": lambda p: {"projects": project_list_active()},
    "project_update": lambda p: project_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "project_delete": lambda p: {"deleted": project_delete(id=p["id"])},
    "project_activate": lambda p: project_update(id=p["id"], is_active=True),
    "project_deactivate": lambda p: project_update(id=p["id"], is_active=False),

    # Phases
    "phase_add": lambda p: phase_add(
        project_id=p["project_id"],
        code=p["code"],
        description=p.get("description")
    ),
    "phase_get": lambda p: phase_get(id=p.get("id"), project_id=p.get("project_id"), code=p.get("code")),
    "phase_list": lambda p: {"phases": phase_list(project_id=p.get("project_id"))},
    "phase_update": lambda p: phase_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "phase_delete": lambda p: {"deleted": phase_delete(id=p["id"])},

    # Tasks (v2: linked to phases, not projects)
    "task_add": lambda p: task_add(
        phase_id=p["phase_id"],  # v2: tasks link to phases
        code=p["code"],
        description=p.get("description")
    ),
    "task_get": lambda p: task_get(id=p.get("id"), phase_id=p.get("phase_id"), code=p.get("code")),
    "task_list": lambda p: {"tasks": task_list(phase_id=p.get("phase_id"), project_id=p.get("project_id"))},
    "task_update": lambda p: task_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "task_delete": lambda p: {"deleted": task_delete(id=p["id"])},

    # Organizations (v2)
    "org_add": lambda p: org_add(
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
    ),
    "org_get": lambda p: org_get(id=p.get("id"), name=p.get("name")),
    "org_list": lambda p: {"organizations": org_list(
        organization_type=p.get("organization_type"),
        country=p.get("country"),
        relationship_status=p.get("relationship_status"),
        active_only=p.get("active_only", True),
    )},
    "org_update": lambda p: org_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "org_delete": lambda p: {"deleted": org_delete(id=p["id"])},
    "org_search": lambda p: {"organizations": org_search(query=p["query"], limit=p.get("limit", 20))},

    # Project-Organization links (v2)
    "project_org_add": lambda p: project_org_add(
        project_id=p["project_id"],
        organization_id=p["organization_id"],
        org_role=p["org_role"],
        contract_value=p.get("contract_value"),
        currency=p.get("currency", "EUR"),
        is_lead=p.get("is_lead", False),
        start_date=p.get("start_date"),
        end_date=p.get("end_date"),
        notes=p.get("notes"),
    ),
    "project_org_get": lambda p: project_org_get(id=p["id"]),
    "project_org_list": lambda p: {"links": project_org_list(
        project_id=p.get("project_id"),
        organization_id=p.get("organization_id"),
        org_role=p.get("org_role"),
    )},
    "project_org_update": lambda p: project_org_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "project_org_delete": lambda p: {"deleted": project_org_delete(id=p["id"])},
    "project_orgs": lambda p: {"organizations": get_project_organizations(project_id=p["project_id"])},
    "org_projects": lambda p: {"projects": get_organization_projects(organization_id=p["organization_id"])},

    # Norms
    "norm_add": lambda p: norm_add(year=p["year"], month=p["month"], hours=p["hours"]),
    "norm_get": lambda p: norm_get(id=p.get("id"), year=p.get("year"), month=p.get("month")),
    "norm_list": lambda p: {"norms": norm_list(year=p.get("year"))},
    "norm_delete": lambda p: {"deleted": norm_delete(id=p["id"])},

    # Exclusions
    "exclusion_add": lambda p: exclusion_add(pattern=p["pattern"]),
    "exclusion_list": lambda p: {"exclusions": exclusion_list()},
    "exclusion_delete": lambda p: {"deleted": exclusion_delete(id=p["id"])},

    # Config
    "config_get": lambda p: {"key": p["key"], "value": config_get(p["key"])},
    "config_set": lambda p: config_set(key=p["key"], value=str(p["value"])),
    "config_list": lambda p: {"settings": config_list()},

    # Init
    "init": lambda p: _init_database(force_reset=p.get("force_reset", False)),
}

# Async operations (reports require awaiting)
ASYNC_OPERATIONS = {
    "report_status": lambda p: generate_report(
        report_type="status",
        account=p.get("account")
    ),
    "report_week": lambda p: generate_report(
        report_type="week",
        account=p.get("account")
    ),
    "report_month": lambda p: generate_report(
        report_type="month",
        account=p.get("account")
    ),
    "report_custom": lambda p: generate_report(
        report_type="custom",
        start_date=p.get("start_date"),
        end_date=p.get("end_date"),
        account=p.get("account")
    ),
}


def _init_database(force_reset: bool = False) -> dict:
    """Initialize empty database."""
    import os

    db_path = get_database_path()

    if database_exists() and not force_reset:
        return {
            "status": "exists",
            "message": "Database already exists. Use force_reset=True to recreate.",
            "path": str(db_path)
        }

    if force_reset and database_exists():
        os.remove(db_path)

    init_database()

    return {
        "status": "created",
        "message": "Empty database created.",
        "path": str(db_path)
    }


async def projects(operations: list[dict]) -> dict:
    """
    Projects and organizations management tool.

    Execute multiple operations in a single call for efficient setup.
    All entities have integer 'id' for update/delete operations.

    IMPORTANT: Use project_list_active when creating calendar events
    to know available projects and their structure (phases/tasks).

    Schema v2 IMPORTANT:
    - Tasks are linked to PHASES (not projects). Hierarchy: PROJECT → PHASE → TASK
    - Organizations have M:N relationship with projects via roles

    Args:
        operations: List of operations to execute. Each operation is a dict with:
            - op: Operation name (see below)
            - Additional parameters depending on operation

    Operations:
        Projects (v2: extended fields):
            - project_add: code, description, is_billable?, is_active?, position?, structure_level?,
                          full_name?, country?, sector?, start_date?, end_date?, contract_value?, currency?, context?
            - project_get: id or code
            - project_list: billable_only?, active_only?
            - project_list_active: Get active projects with phases and tasks.
            - project_update: id, + any project field
            - project_delete: id
            - project_activate/project_deactivate: id

        Phases (require project_id):
            - phase_add: project_id, code, description?
            - phase_get: id or (project_id + code)
            - phase_list: project_id?
            - phase_update: id, code?, description?
            - phase_delete: id

        Tasks (v2: require phase_id, not project_id):
            - task_add: phase_id, code, description?
            - task_get: id or (phase_id + code)
            - task_list: phase_id? or project_id? (lists all tasks for project via phases)
            - task_update: id, code?, description?, phase_id? (to move task)
            - task_delete: id

        Organizations (v2):
            - org_add: name, short_name?, name_local?, organization_type?, parent_org_id?, country?, city?,
                       website?, context?, relationship_status?, first_contact_date?, notes?
            - org_get: id or name
            - org_list: organization_type?, country?, relationship_status?, active_only?
            - org_update: id, + any org field
            - org_delete: id
            - org_search: query, limit?

        Project-Organization Links (v2):
            - project_org_add: project_id, organization_id, org_role, contract_value?, currency?, is_lead?,
                              start_date?, end_date?, notes?
            - project_org_get: id
            - project_org_list: project_id?, organization_id?, org_role?
            - project_org_update: id, org_role?, contract_value?, is_lead?, etc.
            - project_org_delete: id
            - project_orgs: project_id - Get all organizations for a project
            - org_projects: organization_id - Get all projects for an organization

        Norms:
            - norm_add: year, month, hours (upserts)
            - norm_get: id or (year + month)
            - norm_list: year?
            - norm_delete: id

        Exclusions:
            - exclusion_add: pattern
            - exclusion_list
            - exclusion_delete: id

        Config:
            - config_get: key
            - config_set: key, value
            - config_list

        Reports:
            - report_status: account? - Quick WTD/MTD summary
            - report_week: account? - Week report with Excel export
            - report_month: account? - Month report with Excel export
            - report_custom: account?, start_date, end_date - Custom period report

        Init:
            - init: force_reset?

    Returns:
        Dict with results array and summary.

    Example (v2):
        projects(operations=[
            {"op": "org_add", "name": "World Bank", "organization_type": "dfi", "country": "USA"},
            {"op": "project_add", "code": "NEW", "description": "New Project", "is_billable": True, "country": "KG"},
            {"op": "phase_add", "project_id": 1, "code": "P1", "description": "Phase 1"},
            {"op": "task_add", "phase_id": 1, "code": "T1", "description": "Task 1"},
            {"op": "project_org_add", "project_id": 1, "organization_id": 1, "org_role": "donor", "is_lead": True},
        ])
    """
    ensure_database()

    results = []
    success_count = 0
    error_count = 0

    for i, op_data in enumerate(operations):
        op = op_data.get("op")

        if not op:
            results.append({"index": i, "error": "Missing 'op' field"})
            error_count += 1
            continue

        # Check sync operations first
        if op in OPERATIONS:
            try:
                result = OPERATIONS[op](op_data)
                results.append({"index": i, "op": op, "result": result})
                success_count += 1
            except Exception as e:
                results.append({"index": i, "op": op, "error": str(e)})
                error_count += 1
            continue

        # Check async operations (reports)
        if op in ASYNC_OPERATIONS:
            try:
                result = await ASYNC_OPERATIONS[op](op_data)
                results.append({"index": i, "op": op, "result": result})
                success_count += 1
            except Exception as e:
                results.append({"index": i, "op": op, "error": str(e)})
                error_count += 1
            continue

        # Unknown operation
        results.append({"index": i, "op": op, "error": f"Unknown operation: {op}"})
        error_count += 1

    return {
        "results": results,
        "summary": {
            "total": len(operations),
            "success": success_count,
            "errors": error_count
        }
    }
