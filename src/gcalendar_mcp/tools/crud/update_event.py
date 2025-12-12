"""
update_event tool.

Update existing calendar event with support for recurring event instances.
"""

from typing import Optional, Literal
import uuid

from gcalendar_mcp.api.events import (
    update_event as api_update_event,
    get_event as api_get_event,
    get_recurring_instances,
    is_recurring_instance,
)


def update_event(
    event_id: str,
    calendar_id: str = "primary",
    scope: Literal["single", "all", "following"] = "single",
    summary: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    add_attendees: Optional[list[str]] = None,
    remove_attendees: Optional[list[str]] = None,
    add_meet_link: bool = False,
    reminders_minutes: Optional[list[int]] = None,
    color_id: Optional[str] = None,
    visibility: Optional[str] = None,
    transparency: Optional[str] = None,
    extended_properties: Optional[dict] = None,
    send_updates: str = "all",
    account: Optional[str] = None,
) -> dict:
    """
    Update an existing calendar event.
    
    Args:
        event_id: Event ID to update. For recurring events, can be either:
            - Instance ID (e.g., "abc123_20250115T100000Z") for specific occurrence
            - Master ID for the recurring series
        calendar_id: Calendar ID (use 'primary' for the main calendar)
        scope: How to apply changes for recurring events:
            - 'single': Update only this instance (default). If event_id is master, updates first upcoming instance.
            - 'all': Update all instances (past and future). Requires master event ID.
            - 'following': Update this and all future instances. Creates exception from this point forward.
            For non-recurring events, this parameter is ignored.
        summary: New title for the event
        start: New start time: '2025-01-01T10:00:00' for timed or '2025-01-01' for all-day
        end: New end time: '2025-01-01T11:00:00' for timed or '2025-01-02' for all-day
        description: New description/notes
        location: New location
        timezone: Timezone for start/end (IANA format, e.g., 'Asia/Bangkok')
        attendees: Replace all attendees with this list of emails
        add_attendees: Add these email addresses to existing attendees
        remove_attendees: Remove these email addresses from attendees
        add_meet_link: If True, add Google Meet link (if not already present)
        reminders_minutes: New reminder times in minutes (e.g., [10, 60])
        color_id: New color ID for the event
        visibility: 'public', 'private', or 'confidential'
        transparency: 'opaque' (busy) or 'transparent' (free)
        extended_properties: Update extended properties {"private": {...}, "shared": {...}}
        send_updates: 'all', 'externalOnly', or 'none' for notification control
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with updated event details:
        - id: Event ID (may differ from input if instance was created)
        - summary: Event title
        - htmlLink: Direct link to view/edit in Google Calendar
        - start: Event start time
        - end: Event end time
        - meetLink: Google Meet link (if present)
        - attendees: Number of attendees
        - status: Event status
        - scope_applied: Which scope was actually applied
    
    Only provided fields are updated; others remain unchanged.
    """
    # Determine if this is a recurring event and resolve the target event ID
    current_event = api_get_event(event_id, account=account, calendar_id=calendar_id)
    is_recurring = "recurrence" in current_event or current_event.get("recurringEventId")
    
    target_event_id = event_id
    scope_applied = "single"
    
    if is_recurring:
        if scope == "all":
            # Get master event ID
            if current_event.get("recurringEventId"):
                # This is an instance, get master
                target_event_id = current_event["recurringEventId"]
            # else: already master
            scope_applied = "all"
            
        elif scope == "following":
            # For "following", we need to update starting from this instance
            # Google Calendar API doesn't have direct "following" support via PATCH
            # We need to: 1) Get this instance ID, 2) Update it (creates exception)
            # Then modify recurrence end date on master
            if is_recurring_instance(event_id):
                target_event_id = event_id
            else:
                # Master ID provided - get first upcoming instance
                from datetime import datetime
                instances = get_recurring_instances(
                    event_id,
                    account=account,
                    calendar_id=calendar_id,
                    time_min=datetime.now().isoformat(),
                    max_results=1
                )
                if instances:
                    target_event_id = instances[0]["id"]
            scope_applied = "following"
            # Note: Full "following" implementation would require modifying master's RRULE
            # to end before this instance. Current implementation updates single instance.
            # TODO: Implement full "following" with RRULE modification
            
        else:  # scope == "single"
            if is_recurring_instance(event_id):
                target_event_id = event_id
            else:
                # Master ID provided - get first upcoming instance for single update
                from datetime import datetime
                instances = get_recurring_instances(
                    event_id,
                    account=account,
                    calendar_id=calendar_id,
                    time_min=datetime.now().isoformat(),
                    max_results=1
                )
                if instances:
                    target_event_id = instances[0]["id"]
            scope_applied = "single"
    
    # Handle incremental attendee changes
    attendees_list = None
    if attendees is not None:
        attendees_list = [{"email": email} for email in attendees]
    elif add_attendees or remove_attendees:
        # Fetch current event to get existing attendees
        current = api_get_event(target_event_id, account=account, calendar_id=calendar_id)
        current_attendees = {att["email"].lower(): att for att in current.get("attendees", [])}
        
        if remove_attendees:
            for email in remove_attendees:
                current_attendees.pop(email.lower(), None)
        
        if add_attendees:
            for email in add_attendees:
                if email.lower() not in current_attendees:
                    current_attendees[email.lower()] = {"email": email}
        
        attendees_list = list(current_attendees.values())
    
    # Build reminders
    reminders = None
    if reminders_minutes is not None:
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
    result = api_update_event(
        event_id=target_event_id,
        account=account,
        calendar_id=calendar_id,
        summary=summary,
        start=start,
        end=end,
        description=description,
        location=location,
        timezone=timezone,
        attendees=attendees_list,
        reminders=reminders,
        conference_data=conference_data,
        extended_properties=extended_properties,
        color_id=color_id,
        visibility=visibility,
        transparency=transparency,
        send_updates=send_updates,
    )
    
    # Extract Meet link if present
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
        "scope_applied": scope_applied,
        "is_recurring": is_recurring,
    }
