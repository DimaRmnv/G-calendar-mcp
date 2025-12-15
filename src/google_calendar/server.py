"""
GCalendar MCP Server.

FastMCP server exposing Google Calendar tools for Claude Desktop.
"""

from fastmcp import FastMCP

from google_calendar.tools.crud import (
    list_events,
    create_event,
    get_event,
    update_event,
    delete_event,
    search_events,
    get_freebusy,
)
from google_calendar.tools.reference import list_calendars, list_colors, manage_settings
from google_calendar.tools.attendees import manage_attendees, respond_to_event
from google_calendar.tools.intelligence import batch_operations, find_meeting_slots, weekly_brief
from google_calendar.utils.config import load_config


def _is_time_tracking_enabled() -> bool:
    """Check if time tracking is enabled in config."""
    config = load_config()
    return config.get("time_tracking", {}).get("enabled", False)


# Create server
mcp = FastMCP(
    name="google-calendar",
    instructions="""Google Calendar integration. Multi-account support.

TOOL SELECTION:
Schedule view: list_events (period="today"|"week") or weekly_brief (stats, conflicts)
Event details: get_event (full info, attendees, Meet link)
Search: search_events (text match across title/description/attendees)
Availability: get_freebusy (busy/free check) or find_meeting_slots (cross-timezone slot finder)
Create: create_event (add_meet_link=True for video calls; see docstring for recurrence RRULE examples)
Modify: update_event (scope="single"|"all"|"following" for recurring)
Delete: delete_event (scope="single"|"all" for recurring)
Attendees: manage_attendees (list/add/remove/resend)
Bulk: batch_operations (multiple create/update/delete)
Reference: list_calendars, list_colors, manage_settings (action="get"|"set_timezone"|"list_accounts")

TIME TRACKING (if enabled):
Management: time_tracking(operations=[...]) - batch CRUD for projects/phases/tasks/norms/exclusions/config/init
Reports: time_tracking_report(report_type="status"|"week"|"month"|"custom", output_format="summary"|"excel")

TIME: '2024-12-15T10:00:00' (timed) or '2024-12-15' (all-day). Specify timezone for cross-tz scheduling.

ACCOUNTS:
- When user references calendar by name (e.g., "personal", "work", "family"), call manage_settings(action="list_accounts") to match with configured account names.
- Do not assume default account when user mentions specific calendar. If ambiguous, ask user to clarify.
- 'calendar_id' defaults to 'primary'."""
)

# CRUD tools
mcp.tool(list_events)
mcp.tool(create_event)
mcp.tool(get_event)
mcp.tool(update_event)
mcp.tool(delete_event)
mcp.tool(search_events)
mcp.tool(get_freebusy)

# Reference tools
mcp.tool(list_calendars)
mcp.tool(list_colors)
mcp.tool(manage_settings)

# Attendees tools
mcp.tool(manage_attendees)
mcp.tool(respond_to_event)

# Intelligence tools
mcp.tool(batch_operations)
mcp.tool(find_meeting_slots)
mcp.tool(weekly_brief)

# Time tracking tools (conditional) - 2 tools instead of 9 for token efficiency
if _is_time_tracking_enabled():
    from google_calendar.tools.time_tracking import time_tracking, time_tracking_report

    mcp.tool(time_tracking)
    mcp.tool(time_tracking_report)


def serve():
    """Run MCP server."""
    mcp.run()


if __name__ == "__main__":
    serve()
