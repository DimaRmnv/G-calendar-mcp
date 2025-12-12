"""
get_freebusy tool.

Check free/busy availability across calendars.
"""

from typing import Optional
from datetime import datetime, timedelta

from gcalendar_mcp.api.freebusy import get_freebusy as api_get_freebusy
from gcalendar_mcp.api.client import get_user_timezone


def get_freebusy(
    time_min: str,
    time_max: str,
    calendars: Optional[list[str]] = None,
    timezone: Optional[str] = None,
    account: Optional[str] = None,
) -> dict:
    """
    Query free/busy information for calendars.
    
    Args:
        time_min: Start time boundary. Preferred: '2024-01-01T00:00:00' (uses timeZone parameter or calendar timezone). Also accepts: '2024-01-01T00:00:00Z' or '2024-01-01T00:00:00-08:00'.
        time_max: End time boundary. Preferred: '2024-01-01T23:59:59' (uses timeZone parameter or calendar timezone). Also accepts: '2024-01-01T23:59:59Z' or '2024-01-01T23:59:59-08:00'.
        calendars: List of calendar IDs to check. Defaults to ['primary'] if not specified.
        timezone: Timezone for the query (IANA format, e.g., 'Asia/Bangkok')
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - timeMin: Start of queried range
        - timeMax: End of queried range
        - calendars: Dict mapping calendar ID to busy periods
            - busy: List of {start, end} busy time blocks
            - errors: Any errors accessing this calendar
    
    Use this tool to check availability before scheduling meetings.
    Note: Only returns busy times; empty periods are free.
    """
    # Default to primary calendar
    if not calendars:
        calendars = ["primary"]
    
    # Get user timezone if not specified
    if not timezone:
        timezone = get_user_timezone(account)
    
    # Call API
    result = api_get_freebusy(
        time_min=time_min,
        time_max=time_max,
        calendars=calendars,
        account=account,
        timezone=timezone,
    )
    
    # Format response with cleaner structure
    calendars_result = {}
    for cal_id, cal_data in result.get("calendars", {}).items():
        calendars_result[cal_id] = {
            "busy": cal_data.get("busy", []),
            "errors": cal_data.get("errors", []),
        }
    
    return {
        "timeMin": result.get("timeMin"),
        "timeMax": result.get("timeMax"),
        "calendars": calendars_result,
    }
