"""
Google Calendar Calendars API wrapper.

Handles:
- List calendars (accessible by user)
- Get calendar details
- Create/update/delete calendars (secondary)
"""

from typing import Optional

from google_calendar.api.client import get_service


def list_calendars(
    account: Optional[str] = None,
    show_deleted: bool = False,
    show_hidden: bool = False,
) -> list[dict]:
    """
    List all calendars accessible by user.
    
    Returns list of calendar entries with:
    - id: Calendar ID (use for API calls)
    - summary: Calendar name
    - description: Calendar description
    - primary: True if user's primary calendar
    - accessRole: "owner", "writer", "reader", "freeBusyReader"
    - backgroundColor: Hex color
    - timeZone: Calendar timezone
    """
    service = get_service(account)
    
    calendars = []
    page_token = None
    
    while True:
        params = {
            "showDeleted": show_deleted,
            "showHidden": show_hidden,
        }
        
        if page_token:
            params["pageToken"] = page_token
        
        result = service.calendarList().list(**params).execute()
        
        for item in result.get("items", []):
            calendars.append({
                "id": item.get("id"),
                "summary": item.get("summary"),
                "description": item.get("description"),
                "primary": item.get("primary", False),
                "accessRole": item.get("accessRole"),
                "backgroundColor": item.get("backgroundColor"),
                "timeZone": item.get("timeZone"),
                "selected": item.get("selected", False),
            })
        
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    
    return calendars


def get_calendar(
    calendar_id: str = "primary",
    account: Optional[str] = None,
) -> dict:
    """
    Get calendar details.
    
    Returns calendar resource with summary, description, timezone, etc.
    """
    service = get_service(account)
    
    return service.calendars().get(calendarId=calendar_id).execute()


def get_calendar_colors(account: Optional[str] = None) -> dict:
    """
    Get available calendar and event colors.
    
    Returns:
        {
            "calendar": {color_id: {"background": "#hex", "foreground": "#hex"}},
            "event": {color_id: {"background": "#hex", "foreground": "#hex"}}
        }
    """
    service = get_service(account)
    
    result = service.colors().get().execute()
    
    return {
        "calendar": result.get("calendar", {}),
        "event": result.get("event", {}),
    }
