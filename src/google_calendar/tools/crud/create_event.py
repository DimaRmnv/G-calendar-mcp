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

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        summary: Title of the event
        start: Event start time: '2025-01-01T10:00:00' for timed events or '2025-01-01' for all-day events
        end: Event end time: '2025-01-01T11:00:00' for timed events or '2025-01-02' for all-day events (exclusive)
        account: Google account name ("work", "personal", etc.). REQUIRED when user specifies calendar. Call manage_settings(action="list_accounts") first to get available account names.
        calendar_id: Calendar within account (use 'primary' for main calendar)
        description: Description/notes for the event
        location: Location of the event
        timezone: Timezone as IANA name (e.g., Asia/Bangkok). Applied to naive datetime strings.
        attendees: List of attendee email addresses to invite
        add_meet_link: If True, generate Google Meet link
        reminders_minutes: Reminder times in minutes before event (e.g., [10, 60])
        recurrence: RRULE format. Examples:
            - Daily for 5 days: ["RRULE:FREQ=DAILY;COUNT=5"]
            - Every weekday: ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]
            - Every Monday and Wednesday: ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"]
            - Monthly on 15th: ["RRULE:FREQ=MONTHLY;BYMONTHDAY=15"]
        color_id: Color ID (use list_colors to see options)
        visibility: 'public' or 'private'
        transparency: 'opaque' (busy) or 'transparent' (free)
        extended_properties: {"private": {"key": "value"}, "shared": {"key": "value"}}
        send_updates: 'all', 'externalOnly', or 'none'
    
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
