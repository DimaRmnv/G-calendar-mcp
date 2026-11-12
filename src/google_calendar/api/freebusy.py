"""
Google Calendar FreeBusy API wrapper.

Handles:
- Query free/busy information across calendars
"""

from typing import Optional

from google_calendar.api.client import execute_with_retry, get_service
from google_calendar.api.timeutil import to_rfc3339


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
        time_min: Start of time range (ISO 8601; without an offset it is local to `timezone`)
        time_max: End of time range (ISO 8601; without an offset it is local to `timezone`)
        calendars: List of calendar IDs to check
        account: Account name
        timezone: IANA zone for naive bounds and for the response
    
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
        "timeMin": to_rfc3339(time_min, timezone),
        "timeMax": to_rfc3339(time_max, timezone),
        "items": [{"id": cal_id} for cal_id in calendars],
    }

    if timezone:
        body["timeZone"] = timezone

    result = execute_with_retry(service.freebusy().query(body=body), account)

    return {
        "timeMin": result.get("timeMin"),
        "timeMax": result.get("timeMax"),
        "calendars": result.get("calendars", {}),
    }
