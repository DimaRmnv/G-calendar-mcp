"""
search_events tool.

Full-text search across calendar events.
"""

from typing import Optional
from datetime import datetime, timedelta

from google_calendar.api.events import list_events as api_list_events, format_event_summary
from google_calendar.api.client import get_user_timezone


def search_events(
    query: str,
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 25,
    account: Optional[str] = None,
) -> dict:
    """
    Search calendar events by text query.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        query: Search query - matches against summary, description, location, attendees, etc.
        calendar_id: Calendar ID (use 'primary' for the main calendar)
        time_min: Start of search range (ISO 8601). Default: 1 year ago.
        time_max: End of search range (ISO 8601). Default: 1 year ahead.
        max_results: Maximum events to return (1-250, default 25)
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - events: List of matching events (id, summary, start, end, location, status, htmlLink)
        - query: Search query used
        - total: Number of matches found
        - hasMore: Whether more results available
    
    Search matches against:
    - Event title (summary)
    - Description
    - Location
    - Attendee names and emails
    
    Examples:
    - "project review" - find events with these words
    - "john@example.com" - find events with this attendee
    - "Zoom" - find events with Zoom in title/description/location
    """
    # Default time range: 1 year back and forward
    now = datetime.now()
    
    if not time_min:
        time_min = (now - timedelta(days=365)).isoformat()
    
    if not time_max:
        time_max = (now + timedelta(days=365)).isoformat()
    
    # Call API with search query
    result = api_list_events(
        account=account,
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        max_results=min(max_results, 250),
        query=query,
    )
    
    # Format events
    events = [format_event_summary(e) for e in result.get("items", [])]
    
    return {
        "events": events,
        "query": query,
        "total": len(events),
        "hasMore": result.get("nextPageToken") is not None,
    }
