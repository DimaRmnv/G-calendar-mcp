"""
Google Calendar Events API wrapper.

Handles:
- List events with time range and filters
- Get event by ID
- Create event with attendees, conference, reminders
- Update event
- Delete event
- Search events by query
"""

from typing import Optional, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google_calendar.api.client import get_service


def list_events(
    account: Optional[str] = None,
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 50,
    single_events: bool = True,
    order_by: str = "startTime",
    query: Optional[str] = None,
    show_deleted: bool = False,
    page_token: Optional[str] = None,
    private_extended_property: Optional[list[str]] = None,
    shared_extended_property: Optional[list[str]] = None,
) -> dict:
    """
    List events from calendar.
    
    Args:
        account: Account name (uses default if None)
        calendar_id: Calendar ID (default: "primary")
        time_min: Start of time range (ISO 8601)
        time_max: End of time range (ISO 8601)
        max_results: Maximum events to return (1-2500)
        single_events: Expand recurring events into instances
        order_by: "startTime" (requires single_events=True) or "updated"
        query: Free-text search query
        show_deleted: Include deleted events
        page_token: Token for pagination
        private_extended_property: Filter by private properties (key=value)
        shared_extended_property: Filter by shared properties (key=value)
    
    Returns:
        {
            "items": [event resources],
            "nextPageToken": "..." (optional),
            "summary": "calendar name",
            "timeZone": "calendar timezone"
        }
    """
    service = get_service(account)
    
    params = {
        "calendarId": calendar_id,
        "maxResults": min(max_results, 2500),
        "singleEvents": single_events,
        "showDeleted": show_deleted,
    }
    
    if single_events:
        params["orderBy"] = order_by
    
    if time_min:
        # Ensure RFC3339 format with timezone
        params["timeMin"] = _ensure_rfc3339(time_min)
    
    if time_max:
        params["timeMax"] = _ensure_rfc3339(time_max)
    
    if query:
        params["q"] = query
    
    if page_token:
        params["pageToken"] = page_token
    
    if private_extended_property:
        params["privateExtendedProperty"] = private_extended_property
    
    if shared_extended_property:
        params["sharedExtendedProperty"] = shared_extended_property
    
    result = service.events().list(**params).execute()
    
    return {
        "items": result.get("items", []),
        "nextPageToken": result.get("nextPageToken"),
        "summary": result.get("summary"),
        "timeZone": result.get("timeZone"),
    }


def get_event(
    event_id: str,
    account: Optional[str] = None,
    calendar_id: str = "primary",
) -> dict:
    """
    Get event by ID.
    
    Returns full event resource.
    """
    service = get_service(account)
    
    return service.events().get(
        calendarId=calendar_id,
        eventId=event_id
    ).execute()


def create_event(
    summary: str,
    start: str,
    end: str,
    account: Optional[str] = None,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone: Optional[str] = None,
    attendees: Optional[list[dict]] = None,
    reminders: Optional[dict] = None,
    recurrence: Optional[list[str]] = None,
    conference_data: Optional[dict] = None,
    extended_properties: Optional[dict] = None,
    color_id: Optional[str] = None,
    visibility: Optional[str] = None,
    transparency: Optional[str] = None,
    send_updates: str = "all",
) -> dict:
    """
    Create calendar event.
    
    Args:
        summary: Event title
        start: Start time (ISO 8601 or date for all-day)
        end: End time (ISO 8601 or date for all-day)
        account: Account name
        calendar_id: Target calendar
        description: Event description/notes
        location: Event location
        timezone: Timezone for start/end (IANA format)
        attendees: List of {"email": "...", "optional": bool}
        reminders: {"useDefault": bool, "overrides": [{"method": "popup", "minutes": 10}]}
        recurrence: RRULE strings ["RRULE:FREQ=WEEKLY;COUNT=5"]
        conference_data: For Google Meet link generation
        extended_properties: {"private": {...}, "shared": {...}}
        color_id: Event color (1-11)
        visibility: "default", "public", "private", "confidential"
        transparency: "opaque" (busy) or "transparent" (free)
        send_updates: "all", "externalOnly", "none"
    
    Returns:
        Created event resource with ID, htmlLink, etc.
    """
    service = get_service(account)
    
    # Determine if all-day event
    is_all_day = _is_date_only(start)
    
    # Build event body
    event = {
        "summary": summary,
    }
    
    # Start/end times
    if is_all_day:
        event["start"] = {"date": start}
        event["end"] = {"date": end}
    else:
        event["start"] = {"dateTime": start}
        event["end"] = {"dateTime": end}
        if timezone:
            event["start"]["timeZone"] = timezone
            event["end"]["timeZone"] = timezone
    
    # Optional fields
    if description:
        event["description"] = description
    
    if location:
        event["location"] = location
    
    if attendees:
        event["attendees"] = attendees
    
    if reminders:
        event["reminders"] = reminders
    
    if recurrence:
        event["recurrence"] = recurrence
    
    if extended_properties:
        event["extendedProperties"] = extended_properties
    
    if color_id:
        event["colorId"] = color_id
    
    if visibility:
        event["visibility"] = visibility
    
    if transparency:
        event["transparency"] = transparency
    
    # API call params
    params = {
        "calendarId": calendar_id,
        "body": event,
        "sendUpdates": send_updates,
    }
    
    # Conference data requires special handling
    if conference_data:
        event["conferenceData"] = conference_data
        params["conferenceDataVersion"] = 1
    
    return service.events().insert(**params).execute()


def update_event(
    event_id: str,
    account: Optional[str] = None,
    calendar_id: str = "primary",
    summary: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone: Optional[str] = None,
    attendees: Optional[list[dict]] = None,
    reminders: Optional[dict] = None,
    recurrence: Optional[list[str]] = None,
    conference_data: Optional[dict] = None,
    extended_properties: Optional[dict] = None,
    color_id: Optional[str] = None,
    visibility: Optional[str] = None,
    transparency: Optional[str] = None,
    send_updates: str = "all",
) -> dict:
    """
    Update calendar event (patch).
    
    For recurring events:
    - To update a single instance: use the instance ID (contains underscore, e.g., "abc123_20250115T100000Z")
    - To update the master (all instances): use the master event ID
    
    Only provided fields are updated. Others remain unchanged.
    
    Returns:
        Updated event resource.
    """
    service = get_service(account)

    # If timezone provided without start/end, fetch current times and convert
    if timezone and start is None and end is None:
        current = service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()
        current_start = current.get("start", {})
        current_end = current.get("end", {})

        # Extract current times and convert to new timezone
        if "dateTime" in current_start:
            # Parse with offset to get absolute moment
            start_dt_str = current_start["dateTime"]
            end_dt_str = current_end.get("dateTime", "")

            # Parse ISO format (handles +05:00 and Z)
            start_dt = datetime.fromisoformat(start_dt_str.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_dt_str.replace("Z", "+00:00"))

            # Convert to new timezone
            new_tz = ZoneInfo(timezone)
            start_local = start_dt.astimezone(new_tz)
            end_local = end_dt.astimezone(new_tz)

            # Format as local time without offset (timezone will be in separate field)
            start = start_local.strftime("%Y-%m-%dT%H:%M:%S")
            end = end_local.strftime("%Y-%m-%dT%H:%M:%S")
        # else: all-day event - timezone doesn't apply

    # Build patch body
    patch = {}

    if summary is not None:
        patch["summary"] = summary

    if description is not None:
        patch["description"] = description

    if location is not None:
        patch["location"] = location

    if start is not None:
        is_all_day = _is_date_only(start)
        if is_all_day:
            patch["start"] = {"date": start}
        else:
            patch["start"] = {"dateTime": start}
            if timezone:
                patch["start"]["timeZone"] = timezone

    if end is not None:
        is_all_day = _is_date_only(end)
        if is_all_day:
            patch["end"] = {"date": end}
        else:
            patch["end"] = {"dateTime": end}
            if timezone:
                patch["end"]["timeZone"] = timezone
    
    if attendees is not None:
        patch["attendees"] = attendees
    
    if reminders is not None:
        patch["reminders"] = reminders
    
    if recurrence is not None:
        patch["recurrence"] = recurrence
    
    if extended_properties is not None:
        patch["extendedProperties"] = extended_properties
    
    if color_id is not None:
        patch["colorId"] = color_id
    
    if visibility is not None:
        patch["visibility"] = visibility
    
    if transparency is not None:
        patch["transparency"] = transparency
    
    # API call params
    params = {
        "calendarId": calendar_id,
        "eventId": event_id,
        "body": patch,
        "sendUpdates": send_updates,
    }
    
    if conference_data is not None:
        patch["conferenceData"] = conference_data
        params["conferenceDataVersion"] = 1
    
    return service.events().patch(**params).execute()


def delete_event(
    event_id: str,
    account: Optional[str] = None,
    calendar_id: str = "primary",
    send_updates: str = "all",
) -> None:
    """
    Delete calendar event.
    
    For recurring events:
    - To delete a single instance: use the instance ID (contains underscore, e.g., "abc123_20250115T100000Z")
    - To delete the entire series: use the master event ID
    
    Args:
        event_id: Event ID (instance ID for single occurrence, master ID for series)
        account: Account name
        calendar_id: Calendar ID
        send_updates: "all", "externalOnly", "none"
    """
    service = get_service(account)
    
    service.events().delete(
        calendarId=calendar_id,
        eventId=event_id,
        sendUpdates=send_updates
    ).execute()


def quick_add(
    text: str,
    account: Optional[str] = None,
    calendar_id: str = "primary",
    send_updates: str = "all",
) -> dict:
    """
    Create event from natural language text.
    
    Example: "Meeting with John tomorrow at 3pm"
    
    Returns created event resource.
    """
    service = get_service(account)
    
    return service.events().quickAdd(
        calendarId=calendar_id,
        text=text,
        sendUpdates=send_updates
    ).execute()


def move_event(
    event_id: str,
    destination_calendar_id: str,
    account: Optional[str] = None,
    source_calendar_id: str = "primary",
    send_updates: str = "all",
) -> dict:
    """
    Move event to another calendar.
    
    Returns moved event resource.
    """
    service = get_service(account)
    
    return service.events().move(
        calendarId=source_calendar_id,
        eventId=event_id,
        destination=destination_calendar_id,
        sendUpdates=send_updates
    ).execute()


def get_recurring_instances(
    event_id: str,
    account: Optional[str] = None,
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 50,
) -> list[dict]:
    """
    Get instances of a recurring event.
    
    Args:
        event_id: Master event ID (not instance ID)
        account: Account name
        calendar_id: Calendar ID
        time_min: Start of time range for instances
        time_max: End of time range for instances
        max_results: Maximum instances to return
    
    Returns:
        List of event instances with their instance IDs.
    """
    service = get_service(account)
    
    params = {
        "calendarId": calendar_id,
        "eventId": event_id,
        "maxResults": max_results,
    }
    
    if time_min:
        params["timeMin"] = _ensure_rfc3339(time_min)
    
    if time_max:
        params["timeMax"] = _ensure_rfc3339(time_max)
    
    result = service.events().instances(**params).execute()
    return result.get("items", [])


def is_recurring_instance(event_id: str) -> bool:
    """
    Check if event_id is for a recurring instance (vs master event).
    
    Instance IDs contain underscore with timestamp: "abc123_20250115T100000Z"
    Master IDs are simple strings without underscore-timestamp pattern.
    """
    # Instance IDs have format: baseId_YYYYMMDDTHHMMSSZ
    if "_" not in event_id:
        return False
    
    parts = event_id.rsplit("_", 1)
    if len(parts) != 2:
        return False
    
    timestamp_part = parts[1]
    # Check if it looks like a timestamp (8+ chars, starts with digit)
    return len(timestamp_part) >= 8 and timestamp_part[0].isdigit()


# --- Helper functions ---

def _is_date_only(dt_string: str) -> bool:
    """Check if string is date-only (no time component)."""
    # Date only: "2024-12-15"
    # DateTime: "2024-12-15T10:00:00" or "2024-12-15T10:00:00Z" or "2024-12-15T10:00:00+07:00"
    return "T" not in dt_string


def _ensure_rfc3339(dt_string: str) -> str:
    """
    Ensure datetime string is RFC3339 format.

    Handles:
    - Already RFC3339: pass through
    - ISO without timezone: append Z (UTC)
    - Date only: error (should use date format)
    """
    if _is_date_only(dt_string):
        raise ValueError(f"Expected datetime, got date: {dt_string}")

    # Already has timezone indicator
    if dt_string.endswith("Z") or "+" in dt_string or dt_string[-6:-5] == "-":
        return dt_string

    # No timezone - assume UTC
    return dt_string + "Z"


def parse_event_time(event: dict) -> tuple[str, str, bool]:
    """
    Extract start, end, and all-day flag from event.
    
    Returns:
        (start, end, is_all_day)
    """
    start = event.get("start", {})
    end = event.get("end", {})
    
    if "date" in start:
        return start["date"], end.get("date", ""), True
    else:
        return start.get("dateTime", ""), end.get("dateTime", ""), False


def format_event_summary(event: dict) -> dict:
    """
    Format event for display.
    
    Returns simplified event dict.
    """
    start, end, is_all_day = parse_event_time(event)
    
    return {
        "id": event.get("id"),
        "summary": event.get("summary", "(No title)"),
        "start": start,
        "end": end,
        "allDay": is_all_day,
        "location": event.get("location"),
        "status": event.get("status"),
        "htmlLink": event.get("htmlLink"),
        "attendees": len(event.get("attendees", [])),
        "hasConference": "conferenceData" in event,
    }
