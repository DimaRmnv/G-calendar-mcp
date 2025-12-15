"""
manage_calendars tool.

List, get, create, update, delete calendars.
"""

from typing import Optional, Literal

from google_calendar.api.calendars import (
    list_calendars as api_list_calendars,
    get_calendar as api_get_calendar,
    create_calendar as api_create_calendar,
    update_calendar as api_update_calendar,
    delete_calendar as api_delete_calendar,
    get_calendar_acl,
)


def manage_calendars(
    action: Literal["list", "get", "create", "update", "delete"] = "list",
    calendar_id: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    timezone: Optional[str] = None,
    location: Optional[str] = None,
    include_acl: bool = False,
    account: Optional[str] = None,
) -> dict:
    """
    Manage Google Calendars: list, get details, create, update, or delete.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        action: Action to perform:
            - 'list': List all accessible calendars (default)
            - 'get': Get detailed info about a specific calendar
            - 'create': Create a new secondary calendar
            - 'update': Update calendar properties
            - 'delete': Delete a secondary calendar (cannot delete primary)
        calendar_id: Calendar ID (required for get/update/delete, use 'primary' for main calendar)
        summary: Calendar name (required for create, optional for update)
        description: Calendar description (for create/update)
        timezone: IANA timezone, e.g., 'Europe/Kyiv' (for create/update)
        location: Geographic location (for create/update)
        include_acl: If True, include access control list in 'get' response
        account: Account name (uses default if not specified)

    Returns:
        For action='list':
            - calendars: List of calendars with id, summary, description, primary, accessRole, etc.
            - total: Number of calendars

        For action='get':
            - id: Calendar ID
            - summary: Calendar name
            - description: Calendar description
            - timeZone: Calendar timezone
            - location: Geographic location
            - conferenceProperties: Supported conference types
            - acl: Access control list (if include_acl=True)

        For action='create':
            - id: New calendar ID
            - summary: Calendar name
            - timeZone: Calendar timezone
            - created: True

        For action='update':
            - id: Calendar ID
            - summary: Updated name
            - updated: True

        For action='delete':
            - calendar_id: Deleted calendar ID
            - deleted: True

    Examples:
        List all calendars: action="list"
        Get calendar info: action="get", calendar_id="primary"
        Create calendar: action="create", summary="Work Projects", timezone="Europe/Kyiv"
        Update calendar: action="update", calendar_id="abc123", summary="New Name"
        Delete calendar: action="delete", calendar_id="abc123"
    """
    if action == "list":
        return _list_calendars(account)

    elif action == "get":
        if not calendar_id:
            raise ValueError("calendar_id is required for 'get' action")
        return _get_calendar(calendar_id, account, include_acl)

    elif action == "create":
        if not summary:
            raise ValueError("summary is required for 'create' action")
        return _create_calendar(summary, description, timezone, location, account)

    elif action == "update":
        if not calendar_id:
            raise ValueError("calendar_id is required for 'update' action")
        return _update_calendar(calendar_id, summary, description, timezone, location, account)

    elif action == "delete":
        if not calendar_id:
            raise ValueError("calendar_id is required for 'delete' action")
        if calendar_id == "primary":
            raise ValueError("Cannot delete primary calendar")
        return _delete_calendar(calendar_id, account)

    else:
        raise ValueError(f"Unknown action: {action}. Use 'list', 'get', 'create', 'update', or 'delete'.")


def _list_calendars(account: Optional[str]) -> dict:
    """List all accessible calendars."""
    calendars = api_list_calendars(account=account)

    return {
        "calendars": calendars,
        "total": len(calendars),
    }


def _get_calendar(calendar_id: str, account: Optional[str], include_acl: bool) -> dict:
    """Get detailed calendar information."""
    cal = api_get_calendar(calendar_id=calendar_id, account=account)

    result = {
        "id": cal.get("id"),
        "summary": cal.get("summary"),
        "description": cal.get("description"),
        "timeZone": cal.get("timeZone"),
        "location": cal.get("location"),
        "conferenceProperties": cal.get("conferenceProperties"),
    }

    if include_acl:
        result["acl"] = get_calendar_acl(calendar_id=calendar_id, account=account)

    return result


def _create_calendar(
    summary: str,
    description: Optional[str],
    timezone: Optional[str],
    location: Optional[str],
    account: Optional[str],
) -> dict:
    """Create a new secondary calendar."""
    cal = api_create_calendar(
        summary=summary,
        description=description,
        timezone=timezone,
        location=location,
        account=account,
    )

    return {
        "id": cal.get("id"),
        "summary": cal.get("summary"),
        "timeZone": cal.get("timeZone"),
        "created": True,
    }


def _update_calendar(
    calendar_id: str,
    summary: Optional[str],
    description: Optional[str],
    timezone: Optional[str],
    location: Optional[str],
    account: Optional[str],
) -> dict:
    """Update calendar properties."""
    cal = api_update_calendar(
        calendar_id=calendar_id,
        summary=summary,
        description=description,
        timezone=timezone,
        location=location,
        account=account,
    )

    return {
        "id": cal.get("id"),
        "summary": cal.get("summary"),
        "timeZone": cal.get("timeZone"),
        "updated": True,
    }


def _delete_calendar(calendar_id: str, account: Optional[str]) -> dict:
    """Delete a secondary calendar."""
    api_delete_calendar(calendar_id=calendar_id, account=account)

    return {
        "calendar_id": calendar_id,
        "deleted": True,
    }
