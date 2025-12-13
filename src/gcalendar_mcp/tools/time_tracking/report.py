"""
Report tool for time tracking.

Combines status (quick summary) and full reports with Excel export.
"""

from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

from gcalendar_mcp.tools.time_tracking.database import (
    ensure_database,
    config_get,
    norm_get,
    project_list,
)
from gcalendar_mcp.tools.time_tracking.parser import parse_events_batch, TimeEntry
from gcalendar_mcp.api.client import get_service


REPORTS_DIR = Path.home() / "Downloads" / "Timesheet reports"


def _get_reports_dir() -> Path:
    """Get reports directory, creating if needed."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def _count_workdays(start_date, end_date) -> int:
    """Count workdays between dates."""
    count = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _fetch_events(service, calendar_id: str, start: datetime, end: datetime) -> list[dict]:
    """Fetch events from Google Calendar."""
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=start.isoformat() + "Z" if start.tzinfo is None else start.isoformat(),
        timeMax=end.isoformat() + "Z" if end.tzinfo is None else end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=500,
    ).execute()
    return events_result.get("items", [])


def _calculate_metrics(entries: list[TimeEntry], norm_hours: int, billable_target_pct: float, workdays_elapsed: int) -> dict:
    """Calculate time tracking metrics."""
    active = [e for e in entries if not e.is_excluded]
    valid = [e for e in active if e.is_valid]
    errors = [e for e in active if e.has_errors]

    total_hours = sum(e.duration_hours for e in active)
    billable_hours = sum(e.duration_hours for e in valid if e.is_billable)
    non_billable_hours = sum(e.duration_hours for e in valid if not e.is_billable)

    elapsed_norm = workdays_elapsed * 8 if workdays_elapsed > 0 else 8
    billable_target = norm_hours * (billable_target_pct / 100)
    elapsed_billable_target = elapsed_norm * (billable_target_pct / 100)

    return {
        "total_hours": round(total_hours, 2),
        "billable_hours": round(billable_hours, 2),
        "non_billable_hours": round(non_billable_hours, 2),
        "norm_hours": norm_hours,
        "elapsed_norm": elapsed_norm,
        "billable_target": round(billable_target, 2),
        "on_track_pct": round(total_hours / elapsed_norm * 100, 1) if elapsed_norm > 0 else 0,
        "billable_on_track_pct": round(billable_hours / elapsed_billable_target * 100, 1) if elapsed_billable_target > 0 else 0,
        "entries_total": len(active),
        "entries_valid": len(valid),
        "entries_error": len(errors),
    }


def _group_by_project(entries: list[TimeEntry]) -> dict:
    """Group entries by project."""
    projects = {}
    for entry in entries:
        if entry.is_excluded:
            continue
        code = entry.project_code or "UNTRACKED"
        if code not in projects:
            projects[code] = {"hours": 0, "billable": entry.is_billable if entry.project_code else False, "entries": 0}
        projects[code]["hours"] += entry.duration_hours
        projects[code]["entries"] += 1

    for code in projects:
        projects[code]["hours"] = round(projects[code]["hours"], 2)

    return dict(sorted(projects.items(), key=lambda x: x[1]["hours"], reverse=True))


def _get_error_details(entries: list[TimeEntry]) -> list[dict]:
    """Extract error entries."""
    return [
        {"date": e.date.strftime("%Y-%m-%d"), "hours": e.duration_hours, "summary": e.raw_summary[:100], "errors": e.errors}
        for e in entries if e.has_errors and not e.is_excluded
    ]


def _generate_excel(entries: list[TimeEntry], metrics: dict, period_type: str) -> Path:
    """Generate Excel timesheet report."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        raise ImportError("openpyxl required. Install: pip install openpyxl")

    base_location = config_get("base_location") or ""
    wb = Workbook()
    ws = wb.active
    ws.title = f"{period_type}-to-date"

    # Headers
    headers = ["Date", "Fact hours", "Project", "Project phase", "Location", "Description", "Per diems", "Title", "Comment", "Errors"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")

    # Data
    row = 2
    for entry in entries:
        if entry.is_excluded:
            continue
        desc = f"{entry.task_code} * {entry.description}" if entry.task_code and entry.description else entry.description or entry.raw_summary[:100]
        ws.cell(row=row, column=1, value=entry.date.strftime("%d.%m.%Y"))
        ws.cell(row=row, column=2, value=entry.duration_hours)
        ws.cell(row=row, column=3, value=entry.project_code or "")
        ws.cell(row=row, column=4, value=entry.phase_code or "")
        ws.cell(row=row, column=5, value=base_location)
        ws.cell(row=row, column=6, value=desc)
        ws.cell(row=row, column=7, value="")
        ws.cell(row=row, column=8, value=entry.position or "")
        ws.cell(row=row, column=9, value="")
        ws.cell(row=row, column=10, value="; ".join(entry.errors) if entry.errors else "")
        row += 1

    # Column widths
    widths = [12, 10, 12, 15, 12, 80, 10, 30, 15, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w

    # Save
    reports_dir = _get_reports_dir()
    filename = f"{datetime.now().strftime('%Y-%m-%d')}_{period_type}_timesheet.xlsx"
    file_path = reports_dir / filename
    wb.save(file_path)
    return file_path


async def time_tracking_report(
    report_type: str = "status",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_format: str = "summary",
    account: Optional[str] = None,
) -> dict:
    """
    Time tracking report and status tool.

    Args:
        report_type: 'status' (quick WTD/MTD), 'week', 'month', or 'custom'
        start_date: Start date for custom (YYYY-MM-DD)
        end_date: End date for custom (YYYY-MM-DD)
        output_format: 'summary' or 'excel'
        account: Google account name

    Returns:
        For status: week/month summaries with on-track percentages
        For reports: detailed metrics, by_project breakdown, errors list
        For excel: includes file_path to generated report

    Examples:
        - Quick status: report_type="status"
        - Monthly report: report_type="month"
        - Excel export: report_type="month", output_format="excel"
        - Custom range: report_type="custom", start_date="2025-12-01", end_date="2025-12-15"
    """
    ensure_database()

    now = datetime.now()
    today = now.date()

    # Settings
    calendar_id = config_get("work_calendar") or "primary"
    billable_target_pct = float(config_get("billable_target_value") or "75")

    # Get service
    try:
        service = get_service(account)
    except Exception as e:
        return {"error": f"Failed to get calendar service: {str(e)}"}

    # STATUS: Quick WTD/MTD summary
    if report_type == "status":
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = datetime(now.year, now.month, 1)
        end = now.replace(hour=23, minute=59, second=59)

        week_workdays = _count_workdays(week_start.date(), today)
        month_workdays = _count_workdays(month_start.date(), today)

        norm_data = norm_get(year=now.year, month=now.month)
        month_norm = norm_data["hours"] if norm_data else month_workdays * 8

        try:
            events = _fetch_events(service, calendar_id, month_start, end)
        except Exception as e:
            return {"error": f"Failed to fetch events: {str(e)}"}

        entries = parse_events_batch(events)
        active = [e for e in entries if not e.is_excluded]

        week_start_date = week_start.date()
        week_entries = [e for e in active if e.date.date() >= week_start_date]
        month_entries = active

        # Week metrics
        week_total = sum(e.duration_hours for e in week_entries if e.is_valid)
        week_billable = sum(e.duration_hours for e in week_entries if e.is_valid and e.is_billable)
        week_errors = len([e for e in week_entries if e.has_errors])
        week_elapsed = week_workdays * 8
        week_billable_target = week_elapsed * (billable_target_pct / 100)

        # Month metrics
        month_total = sum(e.duration_hours for e in month_entries if e.is_valid)
        month_billable = sum(e.duration_hours for e in month_entries if e.is_valid and e.is_billable)
        month_errors = len([e for e in month_entries if e.has_errors])
        month_elapsed = month_workdays * 8
        month_billable_target = month_elapsed * (billable_target_pct / 100)

        week_on_track = (week_billable / week_billable_target * 100) if week_billable_target > 0 else 0
        month_on_track = (month_billable / month_billable_target * 100) if month_billable_target > 0 else 0

        status_emoji = "✅" if month_on_track >= 95 else "⚠️" if month_on_track >= 80 else "🔴"
        message = (
            f"{status_emoji} MTD: {round(month_total, 1)}h total, {round(month_billable, 1)}h billable "
            f"({round(month_on_track, 0)}% on-track). "
            f"WTD: {round(week_total, 1)}h total, {round(week_billable, 1)}h billable "
            f"({round(week_on_track, 0)}% on-track)."
        )
        if month_errors > 0:
            message += f" ⚠️ {month_errors} events need attention."

        return {
            "week": {
                "total_hours": round(week_total, 2),
                "billable_hours": round(week_billable, 2),
                "on_track_pct": round(week_on_track, 1),
                "workdays": week_workdays,
                "errors": week_errors,
            },
            "month": {
                "total_hours": round(month_total, 2),
                "billable_hours": round(month_billable, 2),
                "norm_hours": month_norm,
                "on_track_pct": round(month_on_track, 1),
                "workdays": month_workdays,
                "errors": month_errors,
            },
            "message": message,
        }

    # REPORT: Week/Month/Custom
    if report_type == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59)
        norm_hours = 40
    elif report_type == "month":
        start = datetime(now.year, now.month, 1)
        end = now.replace(hour=23, minute=59, second=59)
        norm_data = norm_get(year=now.year, month=now.month)
        norm_hours = norm_data["hours"] if norm_data else _count_workdays(start.date(), today) * 8
    elif report_type == "custom":
        if not start_date or not end_date:
            return {"error": "start_date and end_date required for custom report"}
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
        norm_hours = _count_workdays(start.date(), end.date()) * 8
    else:
        return {"error": f"Unknown report_type: {report_type}. Use: status, week, month, custom"}

    workdays_elapsed = _count_workdays(start.date(), min(today, end.date()))

    try:
        events = _fetch_events(service, calendar_id, start, end)
    except Exception as e:
        return {"error": f"Failed to fetch events: {str(e)}"}

    entries = parse_events_batch(events)
    metrics = _calculate_metrics(entries, norm_hours, billable_target_pct, workdays_elapsed)
    by_project = _group_by_project(entries)
    errors = _get_error_details(entries)

    result = {
        "period": {
            "type": report_type,
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "workdays_elapsed": workdays_elapsed,
        },
        "metrics": metrics,
        "by_project": by_project,
        "errors": errors,
    }

    if output_format == "excel":
        try:
            file_path = _generate_excel(entries, metrics, report_type)
            result["file_path"] = str(file_path)
        except Exception as e:
            result["excel_error"] = str(e)

    return result
