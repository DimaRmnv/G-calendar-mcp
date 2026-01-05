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
from google_calendar.api.client import get_service, handle_auth_errors
from google_calendar.utils.config import list_accounts as config_list_accounts, get_default_account


@handle_auth_errors
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
    """Calendar management, colors, settings, and account discovery.

    SKILL REQUIRED: Read calendar-manager skill for event creation workflows.

    Actions:
        ACCOUNTS (call first when user specifies calendar):
        - list_accounts: All configured accounts with emails. Returns [{name, email, is_default}]

        CALENDARS:
        - list: All accessible calendars (default)
        - get: Calendar details. Requires calendar_id
        - create: New secondary calendar. Requires summary
        - update: Modify calendar. Requires calendar_id
        - delete: Remove secondary calendar. Cannot delete primary.

        SETTINGS:
        - settings: User's calendar settings including timezone
        - set_timezone: Update timezone. Requires timezone (IANA format)
        - colors: Available color IDs (1-11 for events)

    ACCOUNT WORKFLOW:
    When user mentions "личный календарь", "personal", "рабочий", "work":
    1. calendars(action="list_accounts")
    2. Match user description to account name or email domain
    3. Pass account= to all subsequent calendar tool calls

    Key params:
        calendar_id: 'primary' for main calendar, or specific ID
        summary: Calendar name (for create)
        timezone: IANA format (for create/update/set_timezone)
        account: Account name from list_accounts

    Examples:
        calendars(action="list_accounts")
        calendars(action="settings", account="work")
        calendars(action="set_timezone", timezone="Asia/Bangkok")
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
    """Set timezone for primary calendar.

    If account not specified, uses default_account from config.
    Finds calendar ID via list_calendars (calendar with primary=True).
    """
    if account is None:
        account = get_default_account()

    # Find primary calendar ID (the "primary" alias doesn't work with calendars API)
    calendars_list = api_list_calendars(account=account)
    primary_cal = next((c for c in calendars_list if c.get("primary")), None)

    if not primary_cal:
        raise ValueError(f"No primary calendar found for account '{account}'")

    cal = api_update_calendar(
        calendar_id=primary_cal["id"],
        timezone=timezone,
        account=account,
    )
    return {
        "timezone": cal.get("timeZone"),
        "updated": True,
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
