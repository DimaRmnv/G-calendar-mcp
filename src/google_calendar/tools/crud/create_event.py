"""
create_event tool.

Create calendar events with attendees, conference links, reminders.
"""

from typing import Optional
import uuid

from google_calendar.api.events import create_event as api_create_event


def create_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    add_meet_link: bool = False,
    reminders_minutes: Optional[list[int]] = None,
    recurrence: Optional[list[str]] = None,
    color_id: Optional[str] = None,
    visibility: Optional[str] = None,
    transparency: Optional[str] = None,
    extended_properties: Optional[dict] = None,
    send_updates: str = "all",
    account: Optional[str] = None,
) -> dict:
    """
    Create a new calendar event.
    
    Args:
        summary: Title of the event
        start: Event start time: '2025-01-01T10:00:00' for timed events or '2025-01-01' for all-day events. Also accepts Google Calendar API object format: {date: '2025-01-01'} or {dateTime: '2025-01-01T10:00:00', timeZone: 'America/Los_Angeles'}
        end: Event end time: '2025-01-01T11:00:00' for timed events or '2025-01-02' for all-day events (exclusive). Also accepts Google Calendar API object format: {date: '2025-01-02'} or {dateTime: '2025-01-01T11:00:00', timeZone: 'America/Los_Angeles'}
        calendar_id: ID of the calendar (use 'primary' for the main calendar)
        description: Description/notes for the event
        location: Location of the event
        timezone: Timezone as IANA Time Zone Database name (e.g., America/Los_Angeles). Takes priority over calendar's default timezone. Only used for timezone-naive datetime strings.
        attendees: List of attendee email addresses to invite
        add_meet_link: If True, automatically generate a Google Meet link for the event
        reminders_minutes: List of reminder times in minutes before event (e.g., [10, 60] for 10min and 1hr reminders)
        recurrence: Recurrence rules in RFC5545 RRULE format. Examples:
            - Daily for 5 days: ["RRULE:FREQ=DAILY;COUNT=5"]
            - Every weekday: ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]
            - Every Monday and Wednesday: ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"]
            - Monthly on 15th: ["RRULE:FREQ=MONTHLY;BYMONTHDAY=15"]
            - Every 2 weeks on Friday: ["RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=FR"]
            - Until specific date: ["RRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20250331T000000Z"]
        color_id: Color ID for the event (use list-colors to see available IDs)
        visibility: Visibility of the event. Use 'public' for public events, 'private' for private events visible to attendees.
        transparency: Whether the event blocks time on the calendar. 'opaque' means busy, 'transparent' means free.
        extended_properties: Extended properties for storing application-specific data. Format: {"private": {"key": "value"}, "shared": {"key": "value"}}
        send_updates: Whether to send notifications about the event creation. 'all' sends to all guests, 'externalOnly' to non-Google Calendar users only, 'none' sends no notifications.
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - id: Event ID
        - summary: Event title
        - htmlLink: Direct link to view/edit event in Google Calendar
        - start: Event start time
        - end: Event end time
        - meetLink: Google Meet link (if add_meet_link=True)
        - attendees: Number of attendees invited
        - status: Event status ('confirmed')
    
    Use this tool to create meetings, appointments, reminders, and other calendar events.
    For inviting attendees, provide their email addresses in the attendees list.
    """
    # Build attendees list
    attendees_list = None
    if attendees:
        attendees_list = [{"email": email} for email in attendees]
    
    # Build reminders
    reminders = None
    if reminders_minutes:
        reminders = {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": m} for m in reminders_minutes
            ]
        }
    
    # Build conference data for Meet link
    conference_data = None
    if add_meet_link:
        conference_data = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        }
    
    # Call API
    result = api_create_event(
        summary=summary,
        start=start,
        end=end,
        account=account,
        calendar_id=calendar_id,
        description=description,
        location=location,
        timezone=timezone,
        attendees=attendees_list,
        reminders=reminders,
        recurrence=recurrence,
        conference_data=conference_data,
        extended_properties=extended_properties,
        color_id=color_id,
        visibility=visibility,
        transparency=transparency,
        send_updates=send_updates,
    )
    
    # Extract Meet link if generated
    meet_link = None
    if result.get("conferenceData"):
        for entry_point in result["conferenceData"].get("entryPoints", []):
            if entry_point.get("entryPointType") == "video":
                meet_link = entry_point.get("uri")
                break
    
    # Format response
    start_time = result.get("start", {})
    end_time = result.get("end", {})
    
    return {
        "id": result.get("id"),
        "summary": result.get("summary"),
        "htmlLink": result.get("htmlLink"),
        "start": start_time.get("dateTime") or start_time.get("date"),
        "end": end_time.get("dateTime") or end_time.get("date"),
        "meetLink": meet_link,
        "attendees": len(result.get("attendees", [])),
        "status": result.get("status"),
    }
