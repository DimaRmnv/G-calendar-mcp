"""
calendars tool.

Unified tool for calendar management, colors, and settings.
Replaces: manage_calendars, list_colors, manage_settings
"""

from typing import Optional, Literal

from google_calendar.api.calendars import (
    list_calendars as api_list_calendars,
    get_calendar as api_get_calendar,
    create_calendar as api_create_calendar,
    update_calendar as api_update_calendar,
    delete_calendar as api_delete_calendar,
    get_calendar_acl,
    get_calendar_colors,
)
from google_calendar.api.client import get_service
from google_calendar.utils.config import list_accounts as config_list_accounts, get_default_account


def calendars(
    action: Literal[
        "list", "get", "create", "update", "delete",
        "colors", "settings", "set_timezone", "list_accounts"
    ] = "list",
    calendar_id: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    timezone: Optional[str] = None,
    location: Optional[str] = None,
    include_acl: bool = False,
    account: Optional[str] = None,
) -> dict:
    """
    Unified tool for calendar management, colors, and account settings.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call calendars(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to subsequent calls
    Do NOT use default account when user specifies a calendar name!

    Args:
        action: Action to perform:

            CALENDAR MANAGEMENT:
            - 'list': List all accessible calendars (default)
            - 'get': Get detailed info about a specific calendar
            - 'create': Create a new secondary calendar
            - 'update': Update calendar properties
            - 'delete': Delete a secondary calendar (cannot delete primary)

            COLORS:
            - 'colors': List available colors for calendars and events

            SETTINGS:
            - 'settings': Get user's calendar settings
            - 'set_timezone': Update timezone (requires timezone parameter)
            - 'list_accounts': List all configured accounts with emails

        calendar_id: Calendar ID (required for get/update/delete, use 'primary' for main)
        summary: Calendar name (required for create, optional for update)
        description: Calendar description (for create/update)
        timezone: IANA timezone, e.g., 'Europe/Kyiv' (for create/update/set_timezone)
        location: Geographic location (for create/update)
        include_acl: If True, include access control list in 'get' response
        account: Account name (uses default if not specified)

    Returns:
        For action='list':
            - calendars: List of calendars with id, summary, description, primary, accessRole
            - total: Number of calendars

        For action='get':
            - id, summary, description, timeZone, location, conferenceProperties
            - acl: Access control list (if include_acl=True)

        For action='create':
            - id: New calendar ID
            - summary, timeZone
            - created: True

        For action='update':
            - id, summary, timeZone
            - updated: True

        For action='delete':
            - calendar_id: Deleted calendar ID
            - deleted: True

        For action='colors':
            - event: Dict of event color IDs (1-11) to {background, foreground}
            - calendar: Dict of calendar color IDs to color info

            Standard event colors:
            1: Lavender, 2: Sage, 3: Grape, 4: Flamingo, 5: Banana,
            6: Tangerine, 7: Peacock, 8: Graphite, 9: Blueberry, 10: Basil, 11: Tomato

        For action='settings':
            - timezone, locale, weekStart, dateFieldOrder, timeFormat, showDeclinedEvents

        For action='set_timezone':
            - timezone: New timezone value
            - updated: True

        For action='list_accounts':
            - accounts: List of {name, email, is_default}
            - default_account: Name of default account

    Examples:
        List calendars: action="list"
        Get calendar: action="get", calendar_id="primary"
        Create calendar: action="create", summary="Work Projects", timezone="Europe/Kyiv"
        Update calendar: action="update", calendar_id="abc123", summary="New Name"
        Delete calendar: action="delete", calendar_id="abc123"
        Get colors: action="colors"
        Get settings: action="settings"
        Set timezone: action="set_timezone", timezone="Europe/Kyiv"
        List accounts: action="list_accounts"
    """
    # Calendar management actions
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

    # Colors action
    elif action == "colors":
        return _get_colors(account)

    # Settings actions
    elif action == "settings":
        return _get_settings(account)

    elif action == "set_timezone":
        if not timezone:
            raise ValueError("timezone parameter required for 'set_timezone' action")
        return _set_timezone(timezone, account)

    elif action == "list_accounts":
        return _list_accounts()

    else:
        valid_actions = "list, get, create, update, delete, colors, settings, set_timezone, list_accounts"
        raise ValueError(f"Unknown action: {action}. Valid actions: {valid_actions}")


# Calendar management helpers
def _list_calendars(account: Optional[str]) -> dict:
    """List all accessible calendars."""
    calendars_list = api_list_calendars(account=account)
    return {
        "calendars": calendars_list,
        "total": len(calendars_list),
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


# Colors helper
def _get_colors(account: Optional[str]) -> dict:
    """Get available colors for calendars and events."""
    colors = get_calendar_colors(account=account)
    return {
        "event": colors.get("event", {}),
        "calendar": colors.get("calendar", {}),
    }


# Settings helpers
def _get_settings(account: Optional[str]) -> dict:
    """Get all calendar settings."""
    service = get_service(account)

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
            pass

    # Normalize format24HourTime to timeFormat
    if "format24HourTime" in result:
        result["timeFormat"] = "24h" if result.pop("format24HourTime") == "true" else "12h"

    return result


def _set_timezone(timezone: str, account: Optional[str]) -> dict:
    """Set calendar timezone."""
    service = get_service(account)

    result = service.settings().patch(
        setting="timezone",
        body={"value": timezone}
    ).execute()

    return {
        "timezone": result.get("value"),
        "updated": True
    }


def _list_accounts() -> dict:
    """List all configured accounts."""
    accounts = config_list_accounts()
    default = get_default_account()

    account_list = []
    for name, info in accounts.items():
        account_list.append({
            "name": name,
            "email": info.get("email", ""),
            "is_default": name == default
        })

    return {
        "accounts": account_list,
        "default_account": default
    }
