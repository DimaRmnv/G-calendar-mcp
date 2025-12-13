"""
Settings management tool for time tracking.

Configure work calendar, billable targets, and base location.
"""

from typing import Optional

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    get_setting,
    set_setting,
    get_all_settings,
)


VALID_SETTINGS = {
    "work_calendar": "Google Calendar ID for work events (e.g., 'primary' or email)",
    "billable_target_type": "How billable target is defined: 'percent' or 'days'",
    "billable_target_value": "Target value (e.g., '75' for 75% or '15' for 15 days)",
    "base_location": "Home city for context (e.g., 'Bangkok', 'Kyiv')",
}


async def time_tracking_config(
    action: str,
    key: Optional[str] = None,
    value: Optional[str] = None,
) -> dict:
    """
    Manage time tracking configuration.
    
    Args:
        action: Operation - 'get', 'set', 'list'
        key: Setting key (required for get/set)
        value: Setting value (required for set)
    
    Returns:
        Dict with operation result:
        - get: {key, value}
        - set: {key, value, status: 'updated'}
        - list: {settings: {...}, descriptions: {...}}
    
    Available settings:
        - work_calendar: Calendar ID (default: 'primary')
        - billable_target_type: 'percent' or 'days'
        - billable_target_value: Target number
        - base_location: Home city
    
    Billable target examples:
        - type='percent', value='75' → 75% of monthly norm must be billable
        - type='days', value='15' → 15 days (120 hours) must be billable
    """
    ensure_database()
    
    if action == "list":
        settings = get_all_settings()
        return {
            "settings": settings,
            "descriptions": VALID_SETTINGS
        }
    
    elif action == "get":
        if not key:
            return {"error": "Key is required"}
        if key not in VALID_SETTINGS:
            return {"error": f"Unknown setting: {key}. Valid: {list(VALID_SETTINGS.keys())}"}
        
        val = get_setting(key)
        return {
            "key": key,
            "value": val,
            "description": VALID_SETTINGS[key]
        }
    
    elif action == "set":
        if not key:
            return {"error": "Key is required"}
        if key not in VALID_SETTINGS:
            return {"error": f"Unknown setting: {key}. Valid: {list(VALID_SETTINGS.keys())}"}
        if value is None:
            return {"error": "Value is required"}
        
        # Validate specific settings
        if key == "billable_target_type" and value not in ("percent", "days"):
            return {"error": "billable_target_type must be 'percent' or 'days'"}
        
        if key == "billable_target_value":
            try:
                num = float(value)
                if num < 0 or num > 100 and get_setting("billable_target_type") == "percent":
                    return {"error": "Percent value must be between 0 and 100"}
            except ValueError:
                return {"error": "billable_target_value must be a number"}
        
        result = set_setting(key, str(value))
        return {"status": "updated", **result}
    
    else:
        return {"error": f"Unknown action: {action}. Use: get, set, list"}
