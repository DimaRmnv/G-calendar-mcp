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


def create_calendar(
    summary: str,
    account: Optional[str] = None,
    description: Optional[str] = None,
    timezone: Optional[str] = None,
    location: Optional[str] = None,
) -> dict:
    """
    Create a new secondary calendar.

    Args:
        summary: Calendar name
        account: Account name
        description: Calendar description
        timezone: IANA timezone (e.g., 'Europe/Kyiv')
        location: Geographic location

    Returns:
        Created calendar resource with id, summary, etc.
    """
    service = get_service(account)

    body = {"summary": summary}

    if description:
        body["description"] = description

    if timezone:
        body["timeZone"] = timezone

    if location:
        body["location"] = location

    return service.calendars().insert(body=body).execute()


def update_calendar(
    calendar_id: str,
    account: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    timezone: Optional[str] = None,
    location: Optional[str] = None,
) -> dict:
    """
    Update calendar properties.

    Args:
        calendar_id: Calendar ID to update
        account: Account name
        summary: New calendar name
        description: New description
        timezone: New timezone (IANA format)
        location: New location

    Returns:
        Updated calendar resource.
    """
    service = get_service(account)

    patch = {}

    if summary is not None:
        patch["summary"] = summary

    if description is not None:
        patch["description"] = description

    if timezone is not None:
        patch["timeZone"] = timezone

    if location is not None:
        patch["location"] = location

    return service.calendars().patch(calendarId=calendar_id, body=patch).execute()


def delete_calendar(
    calendar_id: str,
    account: Optional[str] = None,
) -> None:
    """
    Delete a secondary calendar.

    Note: Cannot delete primary calendar.

    Args:
        calendar_id: Calendar ID to delete
        account: Account name
    """
    service = get_service(account)

    service.calendars().delete(calendarId=calendar_id).execute()


def get_calendar_acl(
    calendar_id: str = "primary",
    account: Optional[str] = None,
) -> list[dict]:
    """
    Get calendar access control list (permissions).

    Returns:
        List of ACL rules with role and scope.
    """
    service = get_service(account)

    result = service.acl().list(calendarId=calendar_id).execute()

    rules = []
    for item in result.get("items", []):
        rules.append({
            "id": item.get("id"),
            "role": item.get("role"),
            "scope_type": item.get("scope", {}).get("type"),
            "scope_value": item.get("scope", {}).get("value"),
        })

    return rules
