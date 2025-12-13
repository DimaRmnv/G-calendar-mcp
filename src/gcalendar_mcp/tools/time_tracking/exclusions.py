"""
Exclusions management tool for time tracking.

Manage event patterns that should be excluded from time tracking (Away, Lunch, etc.).
"""

from typing import Optional

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    add_exclusion,
    list_exclusions,
    delete_exclusion,
)


async def time_tracking_exclusions(
    action: str,
    pattern: Optional[str] = None,
) -> dict:
    """
    Manage exclusion patterns for time tracking.
    
    Events matching these patterns (case-insensitive) are skipped in reports.
    
    Args:
        action: Operation - 'add', 'list', 'delete'
        pattern: Event summary pattern to exclude (required for add/delete)
    
    Returns:
        Dict with operation result:
        - add: {pattern, created: True/False}
        - list: {exclusions: [...], total: N}
        - delete: {deleted: True/False}
    
    Default exclusions (pre-populated):
        - Away
        - Lunch
        - Offline
        - Out of office
    """
    ensure_database()
    
    if action == "add":
        if not pattern:
            return {"error": "Pattern is required"}
        
        try:
            result = add_exclusion(pattern.strip())
            if result["created"]:
                return {"status": "created", "pattern": pattern.strip()}
            else:
                return {"status": "exists", "pattern": pattern.strip()}
        except Exception as e:
            return {"error": str(e)}
    
    elif action == "list":
        exclusions = list_exclusions()
        return {
            "exclusions": exclusions,
            "total": len(exclusions)
        }
    
    elif action == "delete":
        if not pattern:
            return {"error": "Pattern is required"}
        
        deleted = delete_exclusion(pattern.strip())
        if not deleted:
            return {"error": f"Pattern '{pattern}' not found"}
        
        return {"status": "deleted", "pattern": pattern.strip()}
    
    else:
        return {"error": f"Unknown action: {action}. Use: add, list, delete"}
