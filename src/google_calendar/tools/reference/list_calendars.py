"""
list_calendars tool.

List all calendars accessible by user.
"""

from typing import Optional

from google_calendar.api.calendars import list_calendars as api_list_calendars


def list_calendars(
    account: Optional[str] = None,
) -> dict:
    """
    List all calendars accessible by the user.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - calendars: List of calendars with:
            - id: Calendar ID (use this for calendar_id parameter in other tools)
            - summary: Calendar name
            - description: Calendar description
            - primary: True if this is the user's primary calendar
            - accessRole: 'owner', 'writer', 'reader', or 'freeBusyReader'
            - backgroundColor: Hex color code
            - timeZone: Calendar's timezone
            - selected: Whether calendar is shown in the UI
        - total: Number of calendars
    
    Use this tool to discover available calendars and their IDs.
    The primary calendar can always be accessed with calendar_id='primary'.
    Other calendars require their specific ID from this list.
    """
    calendars = api_list_calendars(account=account)
    
    return {
        "calendars": calendars,
        "total": len(calendars),
    }
