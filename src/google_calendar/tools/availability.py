"""
availability tool.

Unified tool for checking availability and finding meeting slots.
Replaces: get_freebusy, find_meeting_slots
"""

from typing import Optional, Literal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google_calendar.api.freebusy import get_freebusy as api_get_freebusy
from google_calendar.api.client import get_user_timezone, handle_auth_errors


@handle_auth_errors
def availability(
    action: Literal["query", "find_slots"] = "query",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    calendars: Optional[list[str]] = None,
    timezone: Optional[str] = None,
    # find_slots specific
    duration_minutes: Optional[int] = None,
    working_hours_start: int = 9,
    working_hours_end: int = 18,
    participant_timezones: Optional[list[str]] = None,
    max_slots: int = 10,
    account: Optional[str] = None,
) -> dict:
    """Check calendar availability and find meeting slots across timezones.

    SKILL REQUIRED: Read calendar-manager skill for scheduling workflows.

    ACCOUNT SELECTION:
    When checking specific calendar, first call calendars(action="list_accounts").

    Actions:
        query: Free/busy status. Returns busy blocks only — gaps are free time.
        find_slots: Available meeting slots respecting working hours across timezones.

    Required: time_min, time_max (ISO datetime or date)

    Params for query:
        calendars: List of calendar IDs. Default ['primary']
        timezone: IANA format for results
        account: Required when user specifies calendar

    Params for find_slots:
        duration_minutes: Required meeting length (required)
        working_hours_start/end: 0-23, default 9-18
        participant_timezones: List of IANA timezones. Slots valid for ALL listed.
        max_slots: Default 10

    Examples:
        availability(action="query", time_min="2025-01-15T00:00:00", time_max="2025-01-15T23:59:59", account="work")
        availability(action="find_slots", time_min="2025-01-15", time_max="2025-01-17",
                     duration_minutes=60, participant_timezones=["Europe/London", "Asia/Bishkek"])
    """
    if action == "query":
        return _query_freebusy(
            time_min=time_min,
            time_max=time_max,
            calendars=calendars,
            timezone=timezone,
            account=account,
        )

    elif action == "find_slots":
        if not duration_minutes:
            raise ValueError("duration_minutes is required for 'find_slots' action")
        return _find_meeting_slots(
            duration_minutes=duration_minutes,
            date_range_start=time_min,
            date_range_end=time_max,
            calendars=calendars,
            working_hours_start=working_hours_start,
            working_hours_end=working_hours_end,
            timezone=timezone,
            participant_timezones=participant_timezones,
            max_slots=max_slots,
            account=account,
        )

    else:
        raise ValueError(f"Unknown action: {action}. Use 'query' or 'find_slots'.")


def _query_freebusy(
    time_min: str,
    time_max: str,
    calendars: Optional[list[str]],
    timezone: Optional[str],
    account: Optional[str],
) -> dict:
    """Query free/busy information for calendars."""
    if not time_min or not time_max:
        raise ValueError("time_min and time_max are required for 'query' action")

    # Default to primary calendar
    if not calendars:
        calendars = ["primary"]

    # Get user timezone if not specified
    if not timezone:
        timezone = get_user_timezone(account)

    # Call API
    result = api_get_freebusy(
        time_min=time_min,
        time_max=time_max,
        calendars=calendars,
        account=account,
        timezone=timezone,
    )

    # Format response with cleaner structure
    calendars_result = {}
    for cal_id, cal_data in result.get("calendars", {}).items():
        calendars_result[cal_id] = {
            "busy": cal_data.get("busy", []),
            "errors": cal_data.get("errors", []),
        }

    return {
        "timeMin": result.get("timeMin"),
        "timeMax": result.get("timeMax"),
        "calendars": calendars_result,
    }


def _find_meeting_slots(
    duration_minutes: int,
    date_range_start: str,
    date_range_end: str,
    calendars: Optional[list[str]],
    working_hours_start: int,
    working_hours_end: int,
    timezone: Optional[str],
    participant_timezones: Optional[list[str]],
    max_slots: int,
    account: Optional[str],
) -> dict:
    """Find available meeting slots across calendars and timezones."""
    if not date_range_start or not date_range_end:
        raise ValueError("time_min and time_max are required for 'find_slots' action")

    # Default timezone
    if not timezone:
        timezone = get_user_timezone(account) or "UTC"

    # Default calendars
    if not calendars:
        calendars = ["primary"]

    # Parse date range
    tz = ZoneInfo(timezone)

    if "T" in date_range_start:
        range_start = datetime.fromisoformat(date_range_start.replace("Z", "+00:00"))
        if range_start.tzinfo is None:
            range_start = range_start.replace(tzinfo=tz)
    else:
        range_start = datetime.strptime(date_range_start, "%Y-%m-%d").replace(tzinfo=tz)

    if "T" in date_range_end:
        range_end = datetime.fromisoformat(date_range_end.replace("Z", "+00:00"))
        if range_end.tzinfo is None:
            range_end = range_end.replace(tzinfo=tz)
    else:
        range_end = datetime.strptime(date_range_end, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=tz
        )

    # Get busy times
    freebusy_result = api_get_freebusy(
        time_min=range_start.isoformat(),
        time_max=range_end.isoformat(),
        calendars=calendars,
        account=account,
        timezone=timezone,
    )

    # Merge all busy periods
    busy_periods = []
    for cal_id, cal_data in freebusy_result.get("calendars", {}).items():
        for busy in cal_data.get("busy", []):
            start = datetime.fromisoformat(busy["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))
            busy_periods.append((start, end))

    # Sort and merge overlapping busy periods
    busy_periods.sort(key=lambda x: x[0])
    merged_busy = []
    for start, end in busy_periods:
        if merged_busy and start <= merged_busy[-1][1]:
            merged_busy[-1] = (merged_busy[-1][0], max(merged_busy[-1][1], end))
        else:
            merged_busy.append((start, end))

    # All timezones to check
    all_timezones = [timezone]
    if participant_timezones:
        all_timezones.extend(participant_timezones)
    tz_objects = [ZoneInfo(t) for t in all_timezones]

    # Find available slots
    slots = []
    duration = timedelta(minutes=duration_minutes)
    slot_start = range_start

    while slot_start + duration <= range_end and len(slots) < max_slots:
        slot_end = slot_start + duration

        # Check if slot is within working hours for all timezones
        is_valid = True
        for tz_obj in tz_objects:
            local_start = slot_start.astimezone(tz_obj)
            local_end = slot_end.astimezone(tz_obj)

            # Must be on same day and within working hours
            if local_start.date() != local_end.date():
                is_valid = False
                break

            if local_start.hour < working_hours_start or local_end.hour > working_hours_end:
                is_valid = False
                break

            if local_end.hour == working_hours_end and local_end.minute > 0:
                is_valid = False
                break

            # Skip weekends
            if local_start.weekday() >= 5:
                is_valid = False
                break

        if is_valid:
            # Check if slot conflicts with busy periods
            conflicts = False
            for busy_start, busy_end in merged_busy:
                if slot_start < busy_end and slot_end > busy_start:
                    conflicts = True
                    # Jump to end of this busy period
                    slot_start = busy_end
                    break

            if not conflicts:
                # Build start times in all timezones
                start_times = {}
                for tz_name, tz_obj in zip(all_timezones, tz_objects):
                    local_time = slot_start.astimezone(tz_obj)
                    start_times[tz_name] = local_time.strftime("%Y-%m-%d %H:%M")

                slots.append({
                    "start": slot_start.astimezone(tz).isoformat(),
                    "end": slot_end.astimezone(tz).isoformat(),
                    "start_times": start_times,
                })
                slot_start = slot_end
            continue

        # Move to next slot (30-minute increments)
        slot_start += timedelta(minutes=30)

        # If we've passed working hours, jump to next day
        local_start = slot_start.astimezone(tz)
        if local_start.hour >= working_hours_end:
            next_day = (local_start + timedelta(days=1)).replace(
                hour=working_hours_start, minute=0, second=0, microsecond=0
            )
            slot_start = next_day.astimezone(ZoneInfo("UTC")).astimezone(tz)

    return {
        "slots": slots,
        "timezone": timezone,
        "duration_minutes": duration_minutes,
        "working_hours": f"{working_hours_start:02d}:00-{working_hours_end:02d}:00",
        "participant_timezones": participant_timezones or [],
        "total_found": len(slots),
    }
