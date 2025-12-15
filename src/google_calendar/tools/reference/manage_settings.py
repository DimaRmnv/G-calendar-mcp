"""
manage_settings tool.

Get or update user's calendar settings including timezone.
"""

from typing import Optional

from google_calendar.api.client import get_service
from google_calendar.utils.config import list_accounts, get_default_account


def manage_settings(
    action: str = "get",
    timezone: Optional[str] = None,
    account: Optional[str] = None,
) -> dict:
    """
    Get or update user's calendar settings, or list configured accounts.

    Args:
        action: Action to perform:
            - 'get': Return all calendar settings for account
            - 'set_timezone': Update timezone (requires timezone parameter)
            - 'list_accounts': List all configured accounts with emails
        timezone: IANA timezone name for set_timezone action (e.g., 'Europe/Kyiv', 'Asia/Bangkok', 'America/New_York')
        account: Account name (uses default if not specified). Not used for list_accounts.

    Returns:
        For action='get':
            - timezone: User's timezone (IANA format)
            - locale: User's locale setting
            - weekStart: First day of week
            - dateFieldOrder: Date format preference
            - timeFormat: '12h' or '24h'
            - showDeclinedEvents: Whether declined events are shown

        For action='set_timezone':
            - timezone: New timezone value
            - updated: True if successful

        For action='list_accounts':
            - accounts: List of {name, email, is_default}
            - default_account: Name of default account

    Examples:
        Get settings: action="get"
        Set timezone: action="set_timezone", timezone="Europe/Kyiv"
        List accounts: action="list_accounts"
    """
    if action == "list_accounts":
        return _list_accounts()

    service = get_service(account)

    if action == "get":
        return _get_settings(service)
    elif action == "set_timezone":
        if not timezone:
            raise ValueError("timezone parameter required for set_timezone action")
        return _set_timezone(service, timezone)
    else:
        raise ValueError(f"Unknown action: {action}. Use 'get', 'set_timezone', or 'list_accounts'.")


def _get_settings(service) -> dict:
    """Get all calendar settings."""
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


def _set_timezone(service, timezone: str) -> dict:
    """Set calendar timezone."""
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
    accounts = list_accounts()
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
