"""
get_event tool.

Get full event details by ID.
"""

from typing import Optional

from google_calendar.api.events import get_event as api_get_event


def get_event(
    event_id: str,
    calendar_id: str = "primary",
    account: Optional[str] = None,
) -> dict:
    """
    Get full details of a calendar event.
    
    Args:
        event_id: Event ID (from list_events or create_event results)
        calendar_id: Calendar ID (use 'primary' for the main calendar)
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with full event details:
        - id: Event ID
        - summary: Event title
        - description: Event description/notes
        - start: Start time (dateTime or date for all-day)
        - end: End time
        - location: Event location
        - status: 'confirmed', 'tentative', or 'cancelled'
        - htmlLink: Direct link to view/edit in Google Calendar
        - attendees: List of attendees with email, responseStatus, organizer flag
        - organizer: Event organizer info
        - creator: Event creator info
        - conferenceData: Google Meet link and details (if present)
        - reminders: Reminder settings
        - recurrence: Recurrence rules (if recurring)
        - extendedProperties: Custom properties (if set)
        - colorId: Event color
        - visibility: Event visibility setting
        - transparency: Whether event blocks time ('opaque' or 'transparent')
    
    Use this tool to get full event details including attendee list with RSVP status,
    description, and conference link. For listing multiple events, use list_events instead.
    """
    result = api_get_event(
        event_id=event_id,
        calendar_id=calendar_id,
        account=account,
    )
    
    # Format attendees for readability
    attendees = []
    for att in result.get("attendees", []):
        attendees.append({
            "email": att.get("email"),
            "displayName": att.get("displayName"),
            "responseStatus": att.get("responseStatus"),  # needsAction, accepted, declined, tentative
            "organizer": att.get("organizer", False),
            "self": att.get("self", False),
            "optional": att.get("optional", False),
        })
    
    # Extract conference link
    meet_link = None
    if result.get("conferenceData"):
        for entry_point in result["conferenceData"].get("entryPoints", []):
            if entry_point.get("entryPointType") == "video":
                meet_link = entry_point.get("uri")
                break
    
    # Format start/end
    start = result.get("start", {})
    end = result.get("end", {})
    
    return {
        "id": result.get("id"),
        "summary": result.get("summary"),
        "description": result.get("description"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "timeZone": start.get("timeZone"),
        "location": result.get("location"),
        "status": result.get("status"),
        "htmlLink": result.get("htmlLink"),
        "attendees": attendees,
        "organizer": result.get("organizer"),
        "creator": result.get("creator"),
        "meetLink": meet_link,
        "reminders": result.get("reminders"),
        "recurrence": result.get("recurrence"),
        "extendedProperties": result.get("extendedProperties"),
        "colorId": result.get("colorId"),
        "visibility": result.get("visibility"),
        "transparency": result.get("transparency"),
        "created": result.get("created"),
        "updated": result.get("updated"),
    }
