"""
weekly_brief tool.

Generate synthesized weekly schedule overview with priorities.
"""

from typing import Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google_calendar.api.events import list_events, format_event_summary
from google_calendar.api.client import get_user_timezone


def weekly_brief(
    start_date: Optional[str] = None,
    calendar_id: str = "primary",
    timezone: Optional[str] = None,
    account: Optional[str] = None,
) -> dict:
    """
    Generate a weekly schedule brief with analysis.
    
    Args:
        start_date: Start of week (date: '2025-01-13'). Default: current week's Monday.
        calendar_id: Calendar ID (use 'primary' for main calendar)
        timezone: Timezone for display (IANA format). Uses calendar timezone if not specified.
        account: Account name (uses default if not specified)
    
    Returns:
        Dictionary with:
        - week_start: Start of week
        - week_end: End of week
        - timezone: Timezone used
        - summary: High-level statistics
            - total_events: Total number of events
            - total_hours: Total scheduled hours
            - busiest_day: Day with most events
            - free_days: Days with no events
        - by_day: Events grouped by day with daily stats
        - highlights: Key events (all-day, many attendees, external meetings)
        - conflicts: Overlapping events detected
    
    Use this tool for:
    - Morning planning ("What's my week look like?")
    - Workload assessment
    - Finding patterns in scheduling
    """
    # Get timezone
    if not timezone:
        timezone = get_user_timezone(account) or "UTC"
    tz = ZoneInfo(timezone)
    
    # Calculate week bounds
    now = datetime.now(tz)
    
    if start_date:
        week_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
    else:
        # Find Monday of current week
        days_since_monday = now.weekday()
        week_start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    
    week_end = week_start + timedelta(days=7)
    
    # Fetch events
    result = list_events(
        account=account,
        calendar_id=calendar_id,
        time_min=week_start.isoformat(),
        time_max=week_end.isoformat(),
        max_results=250,
    )
    
    events = result.get("items", [])
    
    # Process events by day
    days = {}
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        day_key = day_date.strftime("%Y-%m-%d")
        days[day_key] = {
            "name": day_names[i],
            "date": day_key,
            "events": [],
            "total_hours": 0,
        }
    
    # Categorize events
    highlights = []
    all_timed_events = []
    
    for event in events:
        start_data = event.get("start", {})
        end_data = event.get("end", {})
        
        # Parse start time
        if "dateTime" in start_data:
            start_dt = datetime.fromisoformat(start_data["dateTime"].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_data["dateTime"].replace("Z", "+00:00"))
            is_all_day = False
            duration_hours = (end_dt - start_dt).total_seconds() / 3600
        else:
            start_dt = datetime.strptime(start_data.get("date", ""), "%Y-%m-%d").replace(tzinfo=tz)
            is_all_day = True
            duration_hours = 0
        
        local_start = start_dt.astimezone(tz)
        day_key = local_start.strftime("%Y-%m-%d")
        
        if day_key not in days:
            continue
        
        event_summary = {
            "id": event.get("id"),
            "summary": event.get("summary", "(No title)"),
            "start": local_start.strftime("%H:%M") if not is_all_day else "All day",
            "duration_hours": round(duration_hours, 1) if not is_all_day else None,
            "location": event.get("location"),
            "attendees": len(event.get("attendees", [])),
            "has_meet": "conferenceData" in event,
            "is_all_day": is_all_day,
        }
        
        days[day_key]["events"].append(event_summary)
        if not is_all_day:
            days[day_key]["total_hours"] += duration_hours
            all_timed_events.append({
                "start": start_dt,
                "end": end_dt,
                "summary": event.get("summary"),
            })
        
        # Check for highlights
        attendee_count = len(event.get("attendees", []))
        if is_all_day:
            highlights.append({
                "type": "all_day",
                "summary": event.get("summary"),
                "date": day_key,
            })
        elif attendee_count >= 5:
            highlights.append({
                "type": "large_meeting",
                "summary": event.get("summary"),
                "date": day_key,
                "attendees": attendee_count,
            })
    
    # Find conflicts (overlapping events)
    conflicts = []
    all_timed_events.sort(key=lambda x: x["start"])
    
    for i in range(len(all_timed_events) - 1):
        current = all_timed_events[i]
        next_event = all_timed_events[i + 1]
        
        if current["end"] > next_event["start"]:
            conflicts.append({
                "event1": current["summary"],
                "event2": next_event["summary"],
                "overlap_start": next_event["start"].astimezone(tz).strftime("%Y-%m-%d %H:%M"),
            })
    
    # Calculate summary stats
    total_events = sum(len(d["events"]) for d in days.values())
    total_hours = sum(d["total_hours"] for d in days.values())
    
    busiest_day = max(days.values(), key=lambda d: len(d["events"]))
    free_days = [d["name"] for d in days.values() if len(d["events"]) == 0]
    
    # Round hours in days
    for day in days.values():
        day["total_hours"] = round(day["total_hours"], 1)
    
    return {
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": (week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "timezone": timezone,
        "summary": {
            "total_events": total_events,
            "total_hours": round(total_hours, 1),
            "busiest_day": busiest_day["name"] if busiest_day["events"] else None,
            "busiest_day_events": len(busiest_day["events"]),
            "free_days": free_days,
        },
        "by_day": list(days.values()),
        "highlights": highlights[:10],  # Limit highlights
        "conflicts": conflicts,
    }
