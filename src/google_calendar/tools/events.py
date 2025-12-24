"""
events tool.

Unified tool for all event operations: list, create, get, update, delete, search, batch.
Replaces: list_events, create_event, get_event, update_event, delete_event, search_events, batch_operations
"""

from typing import Optional, Literal
from datetime import datetime, timedelta
import uuid

from google_calendar.api.events import (
    list_events as api_list_events,
    create_event as api_create_event,
    get_event as api_get_event,
    update_event as api_update_event,
    delete_event as api_delete_event,
    format_event_summary,
    get_recurring_instances,
    is_recurring_instance,
    move_event as api_move_event,
)
from google_calendar.api.client import get_user_timezone


def events(
    action: Literal["list", "create", "get", "update", "delete", "search", "batch"] = "list",
    # Common parameters
    event_id: Optional[str] = None,
    calendar_id: str = "primary",
    account: Optional[str] = None,
    timezone: Optional[str] = None,
    send_updates: str = "all",
    # List/Search parameters
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    period: Optional[str] = None,
    query: Optional[str] = None,
    max_results: int = 50,
    private_extended_property: Optional[list[str]] = None,
    shared_extended_property: Optional[list[str]] = None,
    # Create/Update parameters
    summary: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    add_attendees: Optional[list[str]] = None,
    remove_attendees: Optional[list[str]] = None,
    add_meet_link: bool = False,
    reminders_minutes: Optional[list[int]] = None,
    recurrence: Optional[list[str]] = None,
    color_id: Optional[str] = None,
    visibility: Optional[str] = None,
    transparency: Optional[str] = None,
    extended_properties: Optional[dict] = None,
    # Update-specific
    scope: Literal["single", "all"] = "single",
    destination_calendar_id: Optional[str] = None,
    # Batch operations
    operations: Optional[list[dict]] = None,
) -> dict:
    """
    Unified tool for all calendar event operations.

    IMPORTANT - TIMEZONE:
    Before creating or updating events, request the user's current timezone
    to ensure events are created in the correct timezone. Use timezone parameter
    with IANA format (e.g., 'Europe/Kyiv', 'Asia/Bishkek').

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call calendars(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    PROJECT CONTEXT (for create/update):
    If user's project context is unclear:
    1. Call projects(operations=[{"op": "project_list_active"}]) to get active projects
    2. Use project information to properly categorize the event

    Args:
        action: Operation to perform:
            - 'list': List events in time range
            - 'create': Create new event
            - 'get': Get full event details
            - 'update': Update existing event
            - 'delete': Delete event
            - 'search': Full-text search
            - 'batch': Multiple operations

        COMMON PARAMETERS:
        event_id: Event ID (required for get/update/delete)
        calendar_id: Calendar ID ('primary' for main calendar)
        account: Account name (uses default if not specified)
        timezone: Timezone (IANA format, e.g., 'Europe/Kyiv')
        send_updates: Notification setting: 'all', 'externalOnly', 'none'

        LIST/SEARCH PARAMETERS:
        time_min: Start time boundary ('2024-01-01T00:00:00')
        time_max: End time boundary
        period: Shorthand: 'today', 'tomorrow', 'yesterday', 'week', 'month'
            (mutually exclusive with time_min/time_max)
        query: Full-text search query (for list and search actions)
        max_results: Maximum events to return (1-250)
        private_extended_property: Filter by private properties (key=value)
        shared_extended_property: Filter by shared properties (key=value)

        CREATE/UPDATE PARAMETERS:
        summary: Event title (required for create)
        start: Start time '2025-01-01T10:00:00' or '2025-01-01' for all-day
        end: End time (required for create)
        description: Event description/notes
        location: Event location
        attendees: Replace all attendees with this list
        add_attendees: Add these emails to existing attendees (update only)
        remove_attendees: Remove these emails from attendees (update only)
        add_meet_link: If True, add Google Meet link
        reminders_minutes: Reminder times in minutes [10, 60]
        recurrence: RRULE format ['RRULE:FREQ=WEEKLY;BYDAY=MO,WE']
        color_id: Color ID (use calendars(action='colors') to see options)
        visibility: 'public' or 'private'
        transparency: 'opaque' (busy) or 'transparent' (free)
        extended_properties: {"private": {...}, "shared": {...}}

        UPDATE-SPECIFIC:
        scope: For recurring events: 'single' or 'all'
        destination_calendar_id: Move event to this calendar

        BATCH PARAMETER:
        operations: List of operations, each with:
            - action: 'create', 'update', or 'delete'
            - For create: summary, start, end, and optional fields
            - For update: event_id and fields to update
            - For delete: event_id

    Returns:
        For action='list':
            - events: List of event summaries
            - calendarName, timeZone, hasMore

        For action='create':
            - id, summary, htmlLink, start, end, meetLink, attendees, status

        For action='get':
            - Full event details including attendees, conferenceData, etc.

        For action='update':
            - id, summary, htmlLink, start, end, meetLink, attendees, status
            - scope_applied, is_recurring, moved_to (if applicable)

        For action='delete':
            - deleted: True, event_id, scope_applied

        For action='search':
            - events: Matching events, query, total, hasMore

        For action='batch':
            - total, succeeded, failed, results

    Examples:
        List today's events: action="list", period="today"
        Create event: action="create", summary="Meeting", start="2025-01-15T10:00:00", end="2025-01-15T11:00:00"
        Get event: action="get", event_id="abc123"
        Update event: action="update", event_id="abc123", summary="New Title"
        Delete event: action="delete", event_id="abc123"
        Search: action="search", query="project review"
        Batch: action="batch", operations=[{"action": "create", ...}, ...]

    TEAMS MEETING LINK:
    To add Teams meeting link to Google Calendar event:
    1. Create Teams event with is_online_meeting=True
    2. Get online_meeting_url from Teams response
    3. Add to location or description parameter

    RECURRENCE EXAMPLES:
    - Daily for 5 days: ["RRULE:FREQ=DAILY;COUNT=5"]
    - Every weekday: ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]
    - Monthly on 15th: ["RRULE:FREQ=MONTHLY;BYMONTHDAY=15"]
    """
    if action == "list":
        return _list_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            period=period,
            query=query,
            max_results=max_results,
            private_extended_property=private_extended_property,
            shared_extended_property=shared_extended_property,
            account=account,
        )

    elif action == "create":
        if not summary:
            raise ValueError("summary is required for 'create' action")
        if not start or not end:
            raise ValueError("start and end are required for 'create' action")
        return _create_event(
            summary=summary,
            start=start,
            end=end,
            calendar_id=calendar_id,
            description=description,
            location=location,
            timezone=timezone,
            attendees=attendees,
            add_meet_link=add_meet_link,
            reminders_minutes=reminders_minutes,
            recurrence=recurrence,
            color_id=color_id,
            visibility=visibility,
            transparency=transparency,
            extended_properties=extended_properties,
            send_updates=send_updates,
            account=account,
        )

    elif action == "get":
        if not event_id:
            raise ValueError("event_id is required for 'get' action")
        return _get_event(
            event_id=event_id,
            calendar_id=calendar_id,
            account=account,
        )

    elif action == "update":
        if not event_id:
            raise ValueError("event_id is required for 'update' action")
        return _update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            scope=scope,
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
            timezone=timezone,
            attendees=attendees,
            add_attendees=add_attendees,
            remove_attendees=remove_attendees,
            add_meet_link=add_meet_link,
            reminders_minutes=reminders_minutes,
            color_id=color_id,
            visibility=visibility,
            transparency=transparency,
            extended_properties=extended_properties,
            destination_calendar_id=destination_calendar_id,
            send_updates=send_updates,
            account=account,
        )

    elif action == "delete":
        if not event_id:
            raise ValueError("event_id is required for 'delete' action")
        return _delete_event(
            event_id=event_id,
            calendar_id=calendar_id,
            scope=scope,
            send_updates=send_updates,
            account=account,
        )

    elif action == "search":
        if not query:
            raise ValueError("query is required for 'search' action")
        return _search_events(
            query=query,
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            account=account,
        )

    elif action == "batch":
        if not operations:
            raise ValueError("operations list is required for 'batch' action")
        return _batch_operations(
            operations=operations,
            calendar_id=calendar_id,
            send_updates=send_updates,
            account=account,
            timezone=timezone,
        )

    else:
        valid_actions = "list, create, get, update, delete, search, batch"
        raise ValueError(f"Unknown action: {action}. Valid actions: {valid_actions}")


# Helper functions

def _get_time_range(
    time_min: Optional[str],
    time_max: Optional[str],
    period: Optional[str],
) -> tuple[str, str]:
    """Build time range from explicit times or period shorthand."""
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


def _list_events(
    calendar_id: str,
    time_min: Optional[str],
    time_max: Optional[str],
    period: Optional[str],
    query: Optional[str],
    max_results: int,
    private_extended_property: Optional[list[str]],
    shared_extended_property: Optional[list[str]],
    account: Optional[str],
) -> dict:
    """List events from a calendar."""
    tz = get_user_timezone(account)
    t_min, t_max = _get_time_range(time_min, time_max, period)

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

    events_list = [format_event_summary(e) for e in result.get("items", [])]

    return {
        "events": events_list,
        "calendarName": result.get("summary"),
        "timeZone": result.get("timeZone"),
        "hasMore": result.get("nextPageToken") is not None,
    }


def _create_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str,
    description: Optional[str],
    location: Optional[str],
    timezone: Optional[str],
    attendees: Optional[list[str]],
    add_meet_link: bool,
    reminders_minutes: Optional[list[int]],
    recurrence: Optional[list[str]],
    color_id: Optional[str],
    visibility: Optional[str],
    transparency: Optional[str],
    extended_properties: Optional[dict],
    send_updates: str,
    account: Optional[str],
) -> dict:
    """Create a new calendar event."""
    attendees_list = None
    if attendees:
        attendees_list = [{"email": email} for email in attendees]

    reminders = None
    if reminders_minutes:
        reminders = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": m} for m in reminders_minutes]
        }

    conference_data = None
    if add_meet_link:
        conference_data = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        }

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

    meet_link = None
    if result.get("conferenceData"):
        for entry_point in result["conferenceData"].get("entryPoints", []):
            if entry_point.get("entryPointType") == "video":
                meet_link = entry_point.get("uri")
                break

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


def _get_event(
    event_id: str,
    calendar_id: str,
    account: Optional[str],
) -> dict:
    """Get full details of a calendar event."""
    result = api_get_event(
        event_id=event_id,
        calendar_id=calendar_id,
        account=account,
    )

    attendees_list = []
    for att in result.get("attendees", []):
        attendees_list.append({
            "email": att.get("email"),
            "displayName": att.get("displayName"),
            "responseStatus": att.get("responseStatus"),
            "organizer": att.get("organizer", False),
            "self": att.get("self", False),
            "optional": att.get("optional", False),
        })

    meet_link = None
    if result.get("conferenceData"):
        for entry_point in result["conferenceData"].get("entryPoints", []):
            if entry_point.get("entryPointType") == "video":
                meet_link = entry_point.get("uri")
                break

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
        "attendees": attendees_list,
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


def _update_event(
    event_id: str,
    calendar_id: str,
    scope: str,
    summary: Optional[str],
    start: Optional[str],
    end: Optional[str],
    description: Optional[str],
    location: Optional[str],
    timezone: Optional[str],
    attendees: Optional[list[str]],
    add_attendees: Optional[list[str]],
    remove_attendees: Optional[list[str]],
    add_meet_link: bool,
    reminders_minutes: Optional[list[int]],
    color_id: Optional[str],
    visibility: Optional[str],
    transparency: Optional[str],
    extended_properties: Optional[dict],
    destination_calendar_id: Optional[str],
    send_updates: str,
    account: Optional[str],
) -> dict:
    """Update an existing calendar event."""
    current_event = api_get_event(event_id, account=account, calendar_id=calendar_id)
    is_recurring = "recurrence" in current_event or current_event.get("recurringEventId")

    target_event_id = event_id
    scope_applied = "single"

    if is_recurring:
        if scope == "all":
            if current_event.get("recurringEventId"):
                target_event_id = current_event["recurringEventId"]
            scope_applied = "all"
        else:
            if is_recurring_instance(event_id):
                target_event_id = event_id
            else:
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

    # Handle move to another calendar
    moved_to = None
    actual_calendar_id = calendar_id
    if destination_calendar_id:
        move_result = api_move_event(
            event_id=target_event_id,
            destination_calendar_id=destination_calendar_id,
            source_calendar_id=calendar_id,
            account=account,
            send_updates=send_updates,
        )
        target_event_id = move_result.get("id", target_event_id)
        moved_to = destination_calendar_id
        actual_calendar_id = destination_calendar_id

    # Check if there are other updates
    has_updates = any([
        summary is not None, start is not None, end is not None,
        description is not None, location is not None, timezone is not None,
        attendees is not None, add_attendees, remove_attendees,
        add_meet_link, reminders_minutes is not None, color_id is not None,
        visibility is not None, transparency is not None, extended_properties is not None,
    ])

    if not has_updates and moved_to:
        start_time = move_result.get("start", {})
        end_time = move_result.get("end", {})
        return {
            "id": move_result.get("id"),
            "summary": move_result.get("summary"),
            "htmlLink": move_result.get("htmlLink"),
            "start": start_time.get("dateTime") or start_time.get("date"),
            "end": end_time.get("dateTime") or end_time.get("date"),
            "meetLink": None,
            "attendees": len(move_result.get("attendees", [])),
            "status": move_result.get("status"),
            "scope_applied": scope_applied,
            "is_recurring": is_recurring,
            "moved_to": moved_to,
        }

    # Handle incremental attendee changes
    attendees_list = None
    if attendees is not None:
        attendees_list = [{"email": email} for email in attendees]
    elif add_attendees or remove_attendees:
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

    reminders = None
    if reminders_minutes is not None:
        reminders = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": m} for m in reminders_minutes]
        }

    conference_data = None
    if add_meet_link:
        conference_data = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        }

    result = api_update_event(
        event_id=target_event_id,
        account=account,
        calendar_id=actual_calendar_id,
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

    meet_link = None
    if result.get("conferenceData"):
        for entry_point in result["conferenceData"].get("entryPoints", []):
            if entry_point.get("entryPointType") == "video":
                meet_link = entry_point.get("uri")
                break

    start_time = result.get("start", {})
    end_time = result.get("end", {})

    response = {
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

    if moved_to:
        response["moved_to"] = moved_to

    return response


def _delete_event(
    event_id: str,
    calendar_id: str,
    scope: str,
    send_updates: str,
    account: Optional[str],
) -> dict:
    """Delete a calendar event."""
    current_event = api_get_event(event_id, account=account, calendar_id=calendar_id)
    is_recurring = "recurrence" in current_event or current_event.get("recurringEventId")

    target_event_id = event_id
    scope_applied = "single"

    if is_recurring:
        if scope == "all":
            if current_event.get("recurringEventId"):
                target_event_id = current_event["recurringEventId"]
            scope_applied = "all"
        else:
            if is_recurring_instance(event_id):
                target_event_id = event_id
            else:
                instances = get_recurring_instances(
                    event_id,
                    account=account,
                    calendar_id=calendar_id,
                    time_min=datetime.now().isoformat(),
                    max_results=1
                )
                if instances:
                    target_event_id = instances[0]["id"]
                else:
                    target_event_id = event_id
                    scope_applied = "all"
            scope_applied = "single"

    api_delete_event(
        event_id=target_event_id,
        calendar_id=calendar_id,
        send_updates=send_updates,
        account=account,
    )

    return {
        "deleted": True,
        "event_id": target_event_id,
        "original_event_id": event_id if event_id != target_event_id else None,
        "scope_applied": scope_applied,
        "is_recurring": is_recurring,
        "send_updates": send_updates,
    }


def _search_events(
    query: str,
    calendar_id: str,
    time_min: Optional[str],
    time_max: Optional[str],
    max_results: int,
    account: Optional[str],
) -> dict:
    """Search calendar events by text query."""
    now = datetime.now()

    if not time_min:
        time_min = (now - timedelta(days=365)).isoformat()

    if not time_max:
        time_max = (now + timedelta(days=365)).isoformat()

    result = api_list_events(
        account=account,
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        max_results=min(max_results, 250),
        query=query,
    )

    events_list = [format_event_summary(e) for e in result.get("items", [])]

    return {
        "events": events_list,
        "query": query,
        "total": len(events_list),
        "hasMore": result.get("nextPageToken") is not None,
    }


def _batch_operations(
    operations: list[dict],
    calendar_id: str,
    send_updates: str,
    account: Optional[str],
    timezone: Optional[str],
) -> dict:
    """Execute multiple calendar operations in batch."""
    results = []
    succeeded = 0
    failed = 0

    for i, op in enumerate(operations):
        op_action = op.get("action")

        try:
            if op_action == "create":
                op_timezone = op.get("timezone") or timezone
                result = api_create_event(
                    summary=op.get("summary", "(No title)"),
                    start=op["start"],
                    end=op["end"],
                    account=account,
                    calendar_id=calendar_id,
                    description=op.get("description"),
                    location=op.get("location"),
                    timezone=op_timezone,
                    attendees=[{"email": e} for e in op.get("attendees", [])] if op.get("attendees") else None,
                    send_updates=send_updates,
                )
                results.append({
                    "index": i,
                    "action": "create",
                    "status": "success",
                    "event_id": result.get("id"),
                    "summary": result.get("summary"),
                })
                succeeded += 1

            elif op_action == "update":
                op_event_id = op.get("event_id")
                if not op_event_id:
                    raise ValueError("event_id required for update")

                update_kwargs = {
                    "event_id": op_event_id,
                    "account": account,
                    "calendar_id": calendar_id,
                    "send_updates": send_updates,
                }

                for field in ["summary", "start", "end", "description", "location"]:
                    if field in op:
                        update_kwargs[field] = op[field]

                op_timezone = op.get("timezone") or timezone
                if op_timezone:
                    update_kwargs["timezone"] = op_timezone

                result = api_update_event(**update_kwargs)
                results.append({
                    "index": i,
                    "action": "update",
                    "status": "success",
                    "event_id": op_event_id,
                })
                succeeded += 1

            elif op_action == "delete":
                op_event_id = op.get("event_id")
                if not op_event_id:
                    raise ValueError("event_id required for delete")

                api_delete_event(
                    event_id=op_event_id,
                    account=account,
                    calendar_id=calendar_id,
                    send_updates=send_updates,
                )
                results.append({
                    "index": i,
                    "action": "delete",
                    "status": "success",
                    "event_id": op_event_id,
                })
                succeeded += 1

            else:
                raise ValueError(f"Unknown action: {op_action}. Use 'create', 'update', or 'delete'.")

        except Exception as e:
            results.append({
                "index": i,
                "action": op_action or "unknown",
                "status": "error",
                "error": str(e),
            })
            failed += 1

    return {
        "total": len(operations),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
