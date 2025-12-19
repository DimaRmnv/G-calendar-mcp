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
from google_calendar.tools.reference import manage_calendars, list_colors, manage_settings
from google_calendar.tools.attendees import manage_attendees, respond_to_event
from google_calendar.tools.intelligence import batch_operations, find_meeting_slots, weekly_brief
from google_calendar.utils.config import load_config


def _is_time_tracking_enabled() -> bool:
    """Check if time tracking is enabled in config."""
    config = load_config()
    return config.get("time_tracking", {}).get("enabled", False)


def _is_contacts_enabled() -> bool:
    """Check if contacts is enabled in config."""
    config = load_config()
    return config.get("contacts", {}).get("enabled", False)


# Create server
mcp = FastMCP(
    name="google-calendar",
    instructions="""Google Calendar integration. Multi-account support.

CRITICAL - ACCOUNT SELECTION:
When user mentions ANY calendar name ("личный", "personal", "рабочий", "work", "family", etc.):
1. FIRST call manage_settings(action="list_accounts") to get available accounts
2. Match user's description to account name
3. Use account="<matched_name>" parameter in subsequent calls
4. NEVER use default account when user specifies a calendar name
Example: "в личном календаре" → list_accounts → find "personal" → account="personal"

ACCOUNTS vs CALENDARS:
- ACCOUNTS = different Google accounts (work, personal). Parameter: account="work"
- CALENDARS = calendars within one account (primary, holidays). Parameter: calendar_id="primary"
- "личный календарь" / "personal calendar" = ACCOUNT, not calendar_id

TOOL SELECTION:
Schedule: list_events (period="today"|"week") or weekly_brief
Create: create_event (add_meet_link=True for video calls)
Modify: update_event (scope="single"|"all"|"following" for recurring)
Delete: delete_event (scope="single"|"all" for recurring)
Search: search_events | Availability: get_freebusy, find_meeting_slots
Attendees: manage_attendees | Bulk: batch_operations
Reference: manage_calendars, list_colors, manage_settings
Move event: update_event(destination_calendar_id=...) - call manage_calendars(action="list") first

TIME TRACKING (if enabled):
time_tracking(operations=[...]) - Use project_list_active when creating events and unsure about available projects.
time_tracking_report(report_type, output_format)

TIME: '2024-12-15T10:00:00' (timed) or '2024-12-15' (all-day)."""
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
mcp.tool(manage_calendars)
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

# Contacts tools (conditional) - extends time_tracking.db with contacts management
if _is_contacts_enabled():
    from google_calendar.tools.contacts import contacts

    mcp.tool(contacts)


def serve():
    """Run MCP server."""
    mcp.run()


if __name__ == "__main__":
    serve()
