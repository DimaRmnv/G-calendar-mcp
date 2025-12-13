"""
Tasks management tool for time tracking.

CRUD operations for project task types: add, list, update, delete.
"""

from typing import Optional

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    create_task,
    get_task,
    list_tasks,
    update_task,
    delete_task,
    get_project,
)


async def time_tracking_tasks(
    action: str,
    project_code: Optional[str] = None,
    task_code: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Manage project task types for time tracking.
    
    Args:
        action: Operation - 'add', 'list', 'update', 'delete'
        project_code: Project code (required for add/update/delete, optional for list)
        task_code: Task code (required for add/update/delete)
        description: Task description
    
    Returns:
        Dict with operation result:
        - add: created task
        - list: {tasks: [...], total: N}
        - update: updated task
        - delete: {deleted: True/False}
    
    Examples:
        - ADB25 tasks: BA (Bank Analysis), BS (Bank Slide), QMR (Quarterly Report)
        - CAYIB tasks: 0.1, 1.2, 2.1 (work package numbers)
        - EDD tasks: OFK, ONI, DRP (phase codes)
    """
    ensure_database()
    
    if action == "add":
        if not project_code:
            return {"error": "Project code is required"}
        if not task_code:
            return {"error": "Task code is required"}
        
        # Verify project exists
        project = get_project(project_code)
        if not project:
            return {"error": f"Project '{project_code}' not found"}
        
        # Check if task exists
        existing = get_task(project_code, task_code)
        if existing:
            return {"error": f"Task '{task_code}' already exists for project '{project_code}'"}
        
        try:
            task = create_task(
                project_code=project_code,
                task_code=task_code,
                description=description
            )
            return {"status": "created", "task": task}
        except Exception as e:
            return {"error": str(e)}
    
    elif action == "list":
        tasks = list_tasks(project_code=project_code)
        result = {
            "tasks": tasks,
            "total": len(tasks)
        }
        if project_code:
            result["project_code"] = project_code.upper()
        return result
    
    elif action == "update":
        if not project_code:
            return {"error": "Project code is required"}
        if not task_code:
            return {"error": "Task code is required"}
        if description is None:
            return {"error": "Description is required for update"}
        
        task = update_task(project_code, task_code, description)
        if not task:
            return {"error": f"Task '{task_code}' not found for project '{project_code}'"}
        
        return {"status": "updated", "task": task}
    
    elif action == "delete":
        if not project_code:
            return {"error": "Project code is required"}
        if not task_code:
            return {"error": "Task code is required"}
        
        deleted = delete_task(project_code, task_code)
        if not deleted:
            return {"error": f"Task '{task_code}' not found for project '{project_code}'"}
        
        return {"status": "deleted", "project_code": project_code.upper(), "task_code": task_code.upper()}
    
    else:
        return {"error": f"Unknown action: {action}. Use: add, list, update, delete"}
