"""
Phases management tool for time tracking.

CRUD operations for project phases: add, list, update, delete.
"""

from typing import Optional

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    create_phase,
    get_phase,
    list_phases,
    update_phase,
    delete_phase,
    get_project,
)


async def time_tracking_phases(
    action: str,
    project_code: Optional[str] = None,
    phase_code: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Manage project phases for time tracking.
    
    Args:
        action: Operation - 'add', 'list', 'update', 'delete'
        project_code: Project code (required for add/update/delete, optional for list)
        phase_code: Phase code (required for add/update/delete)
        description: Phase description
    
    Returns:
        Dict with operation result:
        - add: created phase
        - list: {phases: [...], total: N}
        - update: updated phase
        - delete: {deleted: True/False}
    
    Examples:
        - ADB25 phases: AM, UZ, BD, VN (countries), UZ-Davr, BD-BRAC (banks)
        - CAYIB phases: Eskhata, Humo, Davr (PFIs)
        - BCH phases: AI, ADB, CU, MTNG (internal categories)
    """
    ensure_database()
    
    if action == "add":
        if not project_code:
            return {"error": "Project code is required"}
        if not phase_code:
            return {"error": "Phase code is required"}
        
        # Verify project exists
        project = get_project(project_code)
        if not project:
            return {"error": f"Project '{project_code}' not found"}
        
        # Check if phase exists
        existing = get_phase(project_code, phase_code)
        if existing:
            return {"error": f"Phase '{phase_code}' already exists for project '{project_code}'"}
        
        try:
            phase = create_phase(
                project_code=project_code,
                phase_code=phase_code,
                description=description
            )
            return {"status": "created", "phase": phase}
        except Exception as e:
            return {"error": str(e)}
    
    elif action == "list":
        phases = list_phases(project_code=project_code)
        result = {
            "phases": phases,
            "total": len(phases)
        }
        if project_code:
            result["project_code"] = project_code.upper()
        return result
    
    elif action == "update":
        if not project_code:
            return {"error": "Project code is required"}
        if not phase_code:
            return {"error": "Phase code is required"}
        if description is None:
            return {"error": "Description is required for update"}
        
        phase = update_phase(project_code, phase_code, description)
        if not phase:
            return {"error": f"Phase '{phase_code}' not found for project '{project_code}'"}
        
        return {"status": "updated", "phase": phase}
    
    elif action == "delete":
        if not project_code:
            return {"error": "Project code is required"}
        if not phase_code:
            return {"error": "Phase code is required"}
        
        deleted = delete_phase(project_code, phase_code)
        if not deleted:
            return {"error": f"Phase '{phase_code}' not found for project '{project_code}'"}
        
        return {"status": "deleted", "project_code": project_code.upper(), "phase_code": phase_code.upper()}
    
    else:
        return {"error": f"Unknown action: {action}. Use: add, list, update, delete"}
