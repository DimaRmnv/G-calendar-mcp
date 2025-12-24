"""
Projects management tool.

Single tool for all operations: projects, phases, tasks, norms, exclusions, config, reports.
Supports batch operations for efficient setup.
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
    # Tasks
    task_add, task_get, task_list, task_update, task_delete,
    # Norms
    norm_add, norm_get, norm_list, norm_delete,
    # Exclusions
    exclusion_add, exclusion_list, exclusion_delete,
    # Config
    config_get, config_set, config_list,
)
from google_calendar.tools.projects.report import generate_report


# Operation handlers
OPERATIONS = {
    # Projects
    "project_add": lambda p: project_add(
        code=p["code"],
        description=p["description"],
        is_billable=p.get("is_billable", False),
        is_active=p.get("is_active", True),
        position=p.get("position"),
        structure_level=p.get("structure_level", 1)
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

    # Tasks
    "task_add": lambda p: task_add(
        project_id=p["project_id"],
        code=p["code"],
        description=p.get("description")
    ),
    "task_get": lambda p: task_get(id=p.get("id"), project_id=p.get("project_id"), code=p.get("code")),
    "task_list": lambda p: {"tasks": task_list(project_id=p.get("project_id"))},
    "task_update": lambda p: task_update(id=p["id"], **{k: v for k, v in p.items() if k != "id"}),
    "task_delete": lambda p: {"deleted": task_delete(id=p["id"])},

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
    Projects management tool.

    Execute multiple operations in a single call for efficient setup.
    All entities have integer 'id' for update/delete operations.

    IMPORTANT: Use project_list_active when creating calendar events
    to know available projects and their structure (phases/tasks).

    Args:
        operations: List of operations to execute. Each operation is a dict with:
            - op: Operation name (see below)
            - Additional parameters depending on operation

    Operations:
        Projects (id is returned on add, required for update/delete):
            - project_add: code, description, is_billable?, is_active?, position?, structure_level?
            - project_get: id or code
            - project_list: billable_only?, active_only?
            - project_list_active: Get active projects with phases and tasks.
            - project_update: id, code?, description?, is_billable?, is_active?, position?, structure_level?
            - project_delete: id
            - project_activate/project_deactivate: id

        Phases (require project_id):
            - phase_add: project_id, code, description?
            - phase_get: id or (project_id + code)
            - phase_list: project_id?
            - phase_update: id, code?, description?
            - phase_delete: id

        Tasks (require project_id):
            - task_add: project_id, code, description?
            - task_get: id or (project_id + code)
            - task_list: project_id?
            - task_update: id, code?, description?
            - task_delete: id

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

    Example:
        projects(operations=[
            {"op": "project_add", "code": "NEW", "description": "New Project", "is_billable": True},
            {"op": "phase_add", "project_id": 1, "code": "P1", "description": "Phase 1"},
            {"op": "report_status"},
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
