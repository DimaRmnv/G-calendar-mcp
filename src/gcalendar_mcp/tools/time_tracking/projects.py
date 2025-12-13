"""
Projects management tool for time tracking.

CRUD operations for projects: add, list, update, delete.
"""

from typing import Optional

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    create_project,
    get_project,
    list_projects,
    update_project,
    delete_project,
    get_project_with_details,
)


async def time_tracking_projects(
    action: str,
    code: Optional[str] = None,
    description: Optional[str] = None,
    is_billable: Optional[bool] = None,
    position: Optional[str] = None,
    structure_level: Optional[int] = None,
    billable_only: bool = False,
    include_details: bool = False,
) -> dict:
    """
    Manage time tracking projects.
    
    Args:
        action: Operation to perform - 'add', 'list', 'get', 'update', 'delete'
        code: Project code (required for add/get/update/delete)
        description: Project description (required for add)
        is_billable: Whether project is billable
        position: User's position/role on project
        structure_level: Event format level (1=simple, 2=phase only, 3=full)
        billable_only: For 'list' - filter to billable projects only
        include_details: For 'get' - include phases and tasks
    
    Returns:
        Dict with operation result:
        - add: created project
        - list: {projects: [...], total: N}
        - get: project data (optionally with phases/tasks)
        - update: updated project
        - delete: {deleted: True/False}
    
    Structure levels (level = number of components after PROJECT):
        1: PROJECT * Description (UFSP, CSUM, EFCF)
        2: PROJECT * PHASE * Description (BCH, BDU)
        3: PROJECT * PHASE * TASK * Description (ADB25, CAYIB, EDD)
    """
    ensure_database()
    
    if action == "add":
        if not code:
            return {"error": "Project code is required"}
        if not description:
            return {"error": "Project description is required"}
        
        # Check if exists
        existing = get_project(code)
        if existing:
            return {"error": f"Project '{code}' already exists"}
        
        try:
            project = create_project(
                code=code,
                description=description,
                is_billable=is_billable or False,
                position=position,
                structure_level=structure_level or 1
            )
            return {"status": "created", "project": project}
        except Exception as e:
            return {"error": str(e)}
    
    elif action == "list":
        projects = list_projects(billable_only=billable_only)
        return {
            "projects": projects,
            "total": len(projects),
            "billable_only": billable_only
        }
    
    elif action == "get":
        if not code:
            return {"error": "Project code is required"}
        
        if include_details:
            project = get_project_with_details(code)
        else:
            project = get_project(code)
        
        if not project:
            return {"error": f"Project '{code}' not found"}
        
        return {"project": project}
    
    elif action == "update":
        if not code:
            return {"error": "Project code is required"}
        
        updates = {}
        if description is not None:
            updates["description"] = description
        if is_billable is not None:
            updates["is_billable"] = is_billable
        if position is not None:
            updates["position"] = position
        if structure_level is not None:
            updates["structure_level"] = structure_level
        
        if not updates:
            return {"error": "No fields to update"}
        
        project = update_project(code, **updates)
        if not project:
            return {"error": f"Project '{code}' not found"}
        
        return {"status": "updated", "project": project}
    
    elif action == "delete":
        if not code:
            return {"error": "Project code is required"}
        
        deleted = delete_project(code)
        if not deleted:
            return {"error": f"Project '{code}' not found"}
        
        return {"status": "deleted", "code": code}
    
    else:
        return {"error": f"Unknown action: {action}. Use: add, list, get, update, delete"}
