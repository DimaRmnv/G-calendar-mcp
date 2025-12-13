"""
Quick status tool for time tracking.

Provides fast week-to-date and month-to-date summary without full report generation.
"""

from typing import Optional
from datetime import datetime, timedelta, timezone

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    get_setting,
    get_norm,
)
from gcalendar_mcp.tools.time_tracking.parser import parse_events_batch
from gcalendar_mcp.api.client import get_service


async def time_tracking_status(
    account: Optional[str] = None,
) -> dict:
    """
    Get quick time tracking status for current week and month.
    
    Args:
        account: Google account name (uses default if not specified)
    
    Returns:
        Dict with:
        - week: WTD hours, target, on-track percentage
        - month: MTD hours, target, on-track percentage
        - billable: billable hours breakdown
        - message: Human-readable status summary
    
    Use this for quick progress check. For detailed breakdown, use time_tracking_report.
    """
    ensure_database()
    
    now = datetime.now()
    today = now.date()
    
    # Get settings
    calendar_id = get_setting("work_calendar") or "primary"
    billable_target_type = get_setting("billable_target_type") or "percent"
    billable_target_value = float(get_setting("billable_target_value") or "75")
    
    # Calculate week bounds (naive datetime for comparison)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate month bounds
    month_start = datetime(now.year, now.month, 1)
    
    # End is now
    end = now.replace(hour=23, minute=59, second=59)
    
    # Calculate workdays
    week_workdays = sum(1 for i in range((now.date() - week_start.date()).days + 1) 
                       if (week_start.date() + timedelta(days=i)).weekday() < 5)
    
    month_workdays = 0
    iter_date = month_start.date()
    while iter_date <= today:
        if iter_date.weekday() < 5:
            month_workdays += 1
        iter_date += timedelta(days=1)
    
    # Get norm
    norm_data = get_norm(now.year, now.month)
    month_norm = norm_data["norm_hours"] if norm_data else month_workdays * 8
    week_norm = 40
    
    # Calculate billable targets
    if billable_target_type == "percent":
        month_billable_target = month_norm * (billable_target_value / 100)
        week_billable_target = week_norm * (billable_target_value / 100)
    else:
        month_billable_target = billable_target_value * 8
        week_billable_target = min(billable_target_value * 8 / 4, 40 * 0.75)  # Proportional
    
    # Fetch events for the month (covers week too)
    try:
        service = get_service(account)
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=month_start.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
            maxResults=500,
        ).execute()
        events = events_result.get("items", [])
    except Exception as e:
        return {"error": f"Failed to fetch calendar events: {str(e)}"}
    
    # Parse events
    entries = parse_events_batch(events)
    
    # Filter active (non-excluded) entries
    active_entries = [e for e in entries if not e.is_excluded]
    
    # Split by week/month - compare dates only (no timezone issues)
    week_start_date = week_start.date()
    week_entries = [e for e in active_entries if e.date.date() >= week_start_date]
    month_entries = active_entries
    
    # Calculate hours
    week_total = sum(e.duration_hours for e in week_entries if e.is_valid)
    week_billable = sum(e.duration_hours for e in week_entries if e.is_valid and e.is_billable)
    week_errors = len([e for e in week_entries if e.has_errors])
    
    month_total = sum(e.duration_hours for e in month_entries if e.is_valid)
    month_billable = sum(e.duration_hours for e in month_entries if e.is_valid and e.is_billable)
    month_errors = len([e for e in month_entries if e.has_errors])
    
    # Calculate on-track percentages
    week_elapsed_target = week_workdays * 8
    week_billable_elapsed_target = week_elapsed_target * (billable_target_value / 100) if billable_target_type == "percent" else min(week_billable_target, week_elapsed_target)
    
    month_elapsed_target = month_workdays * 8
    month_billable_elapsed_target = month_elapsed_target * (billable_target_value / 100) if billable_target_type == "percent" else min(month_billable_target, month_elapsed_target)
    
    week_on_track = (week_total / week_elapsed_target * 100) if week_elapsed_target > 0 else 0
    week_billable_on_track = (week_billable / week_billable_elapsed_target * 100) if week_billable_elapsed_target > 0 else 0
    
    month_on_track = (month_total / month_elapsed_target * 100) if month_elapsed_target > 0 else 0
    month_billable_on_track = (month_billable / month_billable_elapsed_target * 100) if month_billable_elapsed_target > 0 else 0
    
    # Generate message
    status_emoji = "✅" if month_billable_on_track >= 95 else "⚠️" if month_billable_on_track >= 80 else "🔴"
    
    message = (
        f"{status_emoji} MTD: {round(month_total, 1)}h total, {round(month_billable, 1)}h billable "
        f"({round(month_billable_on_track, 0)}% on-track). "
        f"WTD: {round(week_total, 1)}h total, {round(week_billable, 1)}h billable "
        f"({round(week_billable_on_track, 0)}% on-track)."
    )
    
    if month_errors > 0 or week_errors > 0:
        message += f" ⚠️ {month_errors} events need attention."
    
    return {
        "week": {
            "total_hours": round(week_total, 2),
            "billable_hours": round(week_billable, 2),
            "norm_hours": week_norm,
            "elapsed_target": week_elapsed_target,
            "on_track_pct": round(week_on_track, 1),
            "billable_on_track_pct": round(week_billable_on_track, 1),
            "workdays_elapsed": week_workdays,
            "errors": week_errors,
        },
        "month": {
            "total_hours": round(month_total, 2),
            "billable_hours": round(month_billable, 2),
            "norm_hours": month_norm,
            "elapsed_target": month_elapsed_target,
            "on_track_pct": round(month_on_track, 1),
            "billable_on_track_pct": round(month_billable_on_track, 1),
            "workdays_elapsed": month_workdays,
            "errors": month_errors,
        },
        "settings": {
            "billable_target_type": billable_target_type,
            "billable_target_value": billable_target_value,
        },
        "message": message,
    }
