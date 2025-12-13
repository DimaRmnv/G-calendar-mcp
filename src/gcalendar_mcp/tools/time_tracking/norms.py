"""
Workday norms management tool for time tracking.

Manage monthly working hours norms by year and month.
"""

from typing import Optional
from datetime import datetime

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    set_norm,
    get_norm,
    list_norms,
    delete_norm,
)


async def time_tracking_norms(
    action: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    norm_hours: Optional[int] = None,
) -> dict:
    """
    Manage workday norms (monthly working hours).
    
    Args:
        action: Operation - 'set', 'get', 'list', 'delete'
        year: Year (e.g., 2025). Defaults to current year for 'list'.
        month: Month (1-12). Required for set/get/delete.
        norm_hours: Working hours for the month. Required for 'set'.
    
    Returns:
        Dict with operation result:
        - set: {year, month, norm_hours}
        - get: norm data or error if not found
        - list: {norms: [...], total: N}
        - delete: {deleted: True/False}
    
    Notes:
        Norms vary by country due to public holidays.
        Typical range: 152-184 hours/month (19-23 working days × 8 hours).
    
    Examples:
        - Thailand 2025: Jan=176, Feb=160, Mar=160...
        - Ukraine 2025: Jan=176, Feb=152, Mar=168...
    """
    ensure_database()
    
    if action == "set":
        if year is None:
            return {"error": "Year is required"}
        if month is None:
            return {"error": "Month is required"}
        if not 1 <= month <= 12:
            return {"error": "Month must be between 1 and 12"}
        if norm_hours is None:
            return {"error": "Norm hours is required"}
        if not 0 < norm_hours <= 248:  # Max ~31 days × 8 hours
            return {"error": "Norm hours must be between 1 and 248"}
        
        try:
            result = set_norm(year, month, norm_hours)
            return {"status": "set", **result}
        except Exception as e:
            return {"error": str(e)}
    
    elif action == "get":
        if year is None:
            year = datetime.now().year
        if month is None:
            return {"error": "Month is required"}
        if not 1 <= month <= 12:
            return {"error": "Month must be between 1 and 12"}
        
        norm = get_norm(year, month)
        if not norm:
            return {"error": f"No norm set for {year}-{month:02d}"}
        
        return {"norm": norm}
    
    elif action == "list":
        norms = list_norms(year=year)
        result = {
            "norms": norms,
            "total": len(norms)
        }
        if year:
            result["year"] = year
        return result
    
    elif action == "delete":
        if year is None:
            return {"error": "Year is required"}
        if month is None:
            return {"error": "Month is required"}
        
        deleted = delete_norm(year, month)
        if not deleted:
            return {"error": f"No norm found for {year}-{month:02d}"}
        
        return {"status": "deleted", "year": year, "month": month}
    
    else:
        return {"error": f"Unknown action: {action}. Use: set, get, list, delete"}
