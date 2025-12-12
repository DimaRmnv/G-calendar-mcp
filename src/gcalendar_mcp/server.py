"""
GCalendar MCP Server.

FastMCP server exposing Google Calendar tools for Claude Desktop.
"""

from fastmcp import FastMCP

from gcalendar_mcp.tools.crud import (
    list_events,
    create_event,
    get_event,
    update_event,
    delete_event,
    search_events,
    get_freebusy,
)
from gcalendar_mcp.tools.reference import list_calendars, list_colors, get_settings
from gcalendar_mcp.tools.attendees import manage_attendees, respond_to_event
from gcalendar_mcp.tools.intelligence import batch_operations, find_meeting_slots, weekly_brief


# Create server
mcp = FastMCP(
    name="gcalendar",
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
Reference: list_calendars, list_colors, get_settings

TIME: '2024-12-15T10:00:00' (timed) or '2024-12-15' (all-day). Specify timezone for cross-tz scheduling.
ACCOUNTS: Use 'account' parameter for non-default. 'calendar_id' defaults to 'primary'."""
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
mcp.tool(get_settings)

# Attendees tools
mcp.tool(manage_attendees)
mcp.tool(respond_to_event)

# Intelligence tools
mcp.tool(batch_operations)
mcp.tool(find_meeting_slots)
mcp.tool(weekly_brief)


def serve():
    """Run MCP server."""
    mcp.run()


if __name__ == "__main__":
    serve()
