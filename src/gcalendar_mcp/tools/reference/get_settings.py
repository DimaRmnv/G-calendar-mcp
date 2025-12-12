"""
get_settings tool.

Get user's calendar settings including timezone.
"""

from typing import Optional

from gcalendar_mcp.api.client import get_service


def get_settings(
    account: Optional[str] = None,
) -> dict:
    """
    Get user's calendar settings.
    
    Args:
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - timezone: User's timezone (IANA format, e.g., 'Asia/Bangkok')
        - locale: User's locale setting
        - weekStart: First day of week ('sunday', 'monday', etc.)
        - dateFieldOrder: Date format preference
        - timeFormat: Time format preference ('12h' or '24h')
        - showDeclinedEvents: Whether declined events are shown
    
    Use this tool to get the user's timezone for scheduling,
    or to understand their calendar display preferences.
    """
    service = get_service(account)
    
    # Fetch relevant settings
    settings_to_fetch = [
        "timezone",
        "locale", 
        "weekStart",
        "dateFieldOrder",
        "format24HourTime",
        "showDeclinedEvents",
    ]
    
    result = {}
    for setting_id in settings_to_fetch:
        try:
            setting = service.settings().get(setting=setting_id).execute()
            result[setting_id] = setting.get("value")
        except Exception:
            # Setting might not exist
            pass
    
    # Normalize format24HourTime to timeFormat
    if "format24HourTime" in result:
        result["timeFormat"] = "24h" if result.pop("format24HourTime") == "true" else "12h"
    
    return result
