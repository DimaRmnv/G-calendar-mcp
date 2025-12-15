"""
list_colors tool.

List available calendar and event colors.
"""

from typing import Optional

from google_calendar.api.calendars import get_calendar_colors


def list_colors(
    account: Optional[str] = None,
) -> dict:
    """
    List available colors for calendars and events.

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
        - event: Dict of event color IDs (1-11) to color info:
            - background: Hex color code for background
            - foreground: Hex color code for text
        - calendar: Dict of calendar color IDs to color info
    
    Use the color ID (e.g., '1', '2', '11') with the color_id parameter
    when creating or updating events.
    
    Standard event colors:
    - 1: Lavender
    - 2: Sage
    - 3: Grape
    - 4: Flamingo
    - 5: Banana
    - 6: Tangerine
    - 7: Peacock
    - 8: Graphite
    - 9: Blueberry
    - 10: Basil
    - 11: Tomato
    """
    colors = get_calendar_colors(account=account)
    
    return {
        "event": colors.get("event", {}),
        "calendar": colors.get("calendar", {}),
    }
