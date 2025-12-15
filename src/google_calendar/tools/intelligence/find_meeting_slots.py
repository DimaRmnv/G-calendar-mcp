"""
find_meeting_slots tool.

Find available time slots across calendars and timezones.
"""

from typing import Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google_calendar.api.freebusy import get_freebusy
from google_calendar.api.client import get_user_timezone


def find_meeting_slots(
    duration_minutes: int,
    date_range_start: str,
    date_range_end: str,
    calendars: Optional[list[str]] = None,
    working_hours_start: int = 9,
    working_hours_end: int = 18,
    timezone: Optional[str] = None,
    participant_timezones: Optional[list[str]] = None,
    max_slots: int = 10,
    account: Optional[str] = None,
) -> dict:
    """
    Find available meeting slots across calendars and timezones.

    IMPORTANT - ACCOUNT SELECTION:
    When user mentions "личный календарь", "personal", "рабочий", "work", etc.:
    1. FIRST call manage_settings(action="list_accounts") to see available accounts
    2. Match user's description to account name (e.g., "личный" → "personal")
    3. Pass account="personal" (or matched name) to this function
    Do NOT use default account when user specifies a calendar name!

    Args:
        duration_minutes: Required meeting duration in minutes
        date_range_start: Start of search range (date: '2025-01-15' or datetime: '2025-01-15T00:00:00')
        date_range_end: End of search range (date: '2025-01-20' or datetime: '2025-01-20T23:59:59')
        calendars: List of calendar IDs to check. Default: ['primary']
        working_hours_start: Start of working hours (0-23, default 9)
        working_hours_end: End of working hours (0-23, default 18)
        timezone: Primary timezone for results (IANA format, e.g., 'Asia/Bangkok'). Uses user's calendar timezone if not specified.
        participant_timezones: List of participant timezones to consider. Slots will be within working hours for ALL timezones.
        max_slots: Maximum number of slots to return (default 10)
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - slots: List of available slots with:
            - start: Start time (ISO 8601 in primary timezone)
            - end: End time (ISO 8601 in primary timezone)
            - start_times: Dict of start times in each participant timezone
        - timezone: Primary timezone used
        - duration_minutes: Requested duration
        - working_hours: Working hours constraint used
        - total_found: Number of slots found
    
    Example: Find 1-hour slots for a meeting with someone in London:
    ```
    find_meeting_slots(
        duration_minutes=60,
        date_range_start="2025-01-15",
        date_range_end="2025-01-17",
        timezone="Asia/Bangkok",
        participant_timezones=["Europe/London"],
        working_hours_start=9,
        working_hours_end=17
    )
    ```
    
    This finds slots that are within 9:00-17:00 in BOTH Bangkok and London.
    """
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
    freebusy_result = get_freebusy(
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
