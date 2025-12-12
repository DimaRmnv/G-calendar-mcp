"""
Google Calendar FreeBusy API wrapper.

Handles:
- Query free/busy information across calendars
"""

from typing import Optional

from gcalendar_mcp.api.client import get_service


def get_freebusy(
    time_min: str,
    time_max: str,
    calendars: list[str],
    account: Optional[str] = None,
    timezone: Optional[str] = None,
) -> dict:
    """
    Query free/busy information for calendars.
    
    Args:
        time_min: Start of time range (ISO 8601)
        time_max: End of time range (ISO 8601)
        calendars: List of calendar IDs to check
        account: Account name
        timezone: Timezone for interpretation (IANA format)
    
    Returns:
        {
            "timeMin": "...",
            "timeMax": "...",
            "calendars": {
                "calendar_id": {
                    "busy": [{"start": "...", "end": "..."}],
                    "errors": [...]  # if any
                }
            }
        }
    """
    service = get_service(account)
    
    body = {
        "timeMin": _ensure_rfc3339(time_min),
        "timeMax": _ensure_rfc3339(time_max),
        "items": [{"id": cal_id} for cal_id in calendars],
    }
    
    if timezone:
        body["timeZone"] = timezone
    
    result = service.freebusy().query(body=body).execute()
    
    return {
        "timeMin": result.get("timeMin"),
        "timeMax": result.get("timeMax"),
        "calendars": result.get("calendars", {}),
    }


def _ensure_rfc3339(dt_string: str) -> str:
    """Ensure datetime string is RFC3339 format."""
    if "T" not in dt_string:
        raise ValueError(f"Expected datetime, got date: {dt_string}")
    
    if dt_string.endswith("Z") or "+" in dt_string[-6:] or dt_string[-6:-5] == "-":
        return dt_string
    
    return dt_string + "Z"
