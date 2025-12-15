"""
list_events tool.

List calendar events with time range, filters, and extended property support.
"""

from typing import Optional
from datetime import datetime, timedelta

from google_calendar.api.events import list_events as api_list_events, format_event_summary
from google_calendar.api.client import get_user_timezone


def _get_time_range(
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    period: Optional[str] = None,
    timezone: Optional[str] = None,
) -> tuple[str, str]:
    """
    Build time range from explicit times or period shorthand.
    
    Periods: today, tomorrow, week, month
    """
    if time_min and time_max:
        return time_min, time_max
    
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if period == "today":
        t_min = today_start
        t_max = today_start + timedelta(days=1)
    elif period == "tomorrow":
        t_min = today_start + timedelta(days=1)
        t_max = today_start + timedelta(days=2)
    elif period == "week":
        t_min = today_start
        t_max = today_start + timedelta(days=7)
    elif period == "month":
        t_min = today_start
        t_max = today_start + timedelta(days=30)
    elif period == "yesterday":
        t_min = today_start - timedelta(days=1)
        t_max = today_start
    else:
        # Default: next 7 days
        t_min = now
        t_max = now + timedelta(days=7)
    
    return t_min.isoformat(), t_max.isoformat()


def list_events(
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    period: Optional[str] = None,
    query: Optional[str] = None,
    max_results: int = 50,
    private_extended_property: Optional[list[str]] = None,
    shared_extended_property: Optional[list[str]] = None,
    account: Optional[str] = None,
) -> dict:
    """
    List events from a calendar.
    
    Args:
        calendar_id: Calendar ID (use 'primary' for the main calendar)
        time_min: Start time boundary. Preferred: '2024-01-01T00:00:00' (uses timeZone parameter or calendar timezone). Also accepts: '2024-01-01T00:00:00Z' or '2024-01-01T00:00:00-08:00'.
        time_max: End time boundary. Preferred: '2024-01-01T23:59:59' (uses timeZone parameter or calendar timezone). Also accepts: '2024-01-01T23:59:59Z' or '2024-01-01T23:59:59-08:00'.
        period: Time filter shorthand. MUTUALLY EXCLUSIVE with time_min/time_max - use one or the other:
            - "today" - today's events
            - "tomorrow" - tomorrow's events  
            - "yesterday" - yesterday's events
            - "week" - next 7 days
            - "month" - next 30 days
            If both period and time_min/time_max provided, time_min/time_max takes priority.
        query: Free text search query (searches summary, description, location, attendees, etc.)
        max_results: Maximum events to return (1-250, default 50)
        private_extended_property: Filter by private extended properties (key=value). Matches events that have all specified properties.
        shared_extended_property: Filter by shared extended properties (key=value). Matches events that have all specified properties.
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - events: List of event summaries (id, summary, start, end, location, status, htmlLink, attendees count, hasConference)
        - calendarName: Name of the calendar
        - timeZone: Calendar's timezone
        - hasMore: Whether more results available
    
    Use this tool to see what's on the calendar for a time period.
    For full event details including attendees list and description, use get_event with the event ID.
    """
    # Get timezone
    tz = get_user_timezone(account)
    
    # Build time range
    t_min, t_max = _get_time_range(time_min, time_max, period, tz)
    
    # Call API
    result = api_list_events(
        account=account,
        calendar_id=calendar_id,
        time_min=t_min,
        time_max=t_max,
        max_results=min(max_results, 250),
        query=query,
        private_extended_property=private_extended_property,
        shared_extended_property=shared_extended_property,
    )
    
    # Format events
    events = [format_event_summary(e) for e in result.get("items", [])]
    
    return {
        "events": events,
        "calendarName": result.get("summary"),
        "timeZone": result.get("timeZone"),
        "hasMore": result.get("nextPageToken") is not None,
    }
