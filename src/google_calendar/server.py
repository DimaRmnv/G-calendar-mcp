"""
GCalendar MCP Server.

FastMCP server exposing Google Calendar tools for Claude Desktop.
Supports both stdio (local) and HTTP (cloud) transport modes.
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


def _is_cloud_mode() -> bool:
    """Check if running in cloud mode."""
    try:
        from google_calendar.settings import settings
        return settings.transport_mode == "http"
    except ImportError:
        return False


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

# Time tracking tools - always enabled
from google_calendar.tools.time_tracking import time_tracking, time_tracking_report

mcp.tool(time_tracking)
mcp.tool(time_tracking_report)

# Contacts tools - always enabled
from google_calendar.tools.contacts import contacts

mcp.tool(contacts)


def create_http_app():
    """
    Create FastAPI app for HTTP transport mode.

    Includes:
    - OAuth callback endpoints
    - API key authentication middleware
    - MCP endpoints
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    from google_calendar.settings import settings
    from google_calendar.oauth_server import oauth_router, validate_access_token

    # Get MCP app first to access its lifespan
    mcp_app = mcp.http_app()

    app = FastAPI(
        title="Google Calendar MCP",
        description="MCP server for Google Calendar integration",
        version="0.1.0",
        lifespan=mcp_app.lifespan  # Required for FastMCP session management
    )

    # Add OAuth router under /mcp/calendar/oauth
    app.include_router(oauth_router, prefix="/mcp/calendar")

    # Authentication middleware
    @app.middleware("http")
    async def check_auth(request: Request, call_next):
        import base64

        # Skip auth check for OAuth endpoints
        if "/oauth" in request.url.path:
            return await call_next(request)

        # Skip for health check
        if request.url.path in ["/health", "/mcp/calendar/health"]:
            return await call_next(request)

        # Skip for docs
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Check if any authentication is configured
        has_api_key = bool(settings.api_key)
        has_oauth = bool(settings.oauth_client_id and settings.oauth_client_secret)

        if not has_api_key and not has_oauth:
            # No auth configured, allow all
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")

        # Try Bearer token (OAuth 2.0 access token or API key)
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Check API key first
            if has_api_key and token == settings.api_key:
                return await call_next(request)
            # Check OAuth token
            if validate_access_token(token):
                return await call_next(request)
            return JSONResponse(
                {"error": "Unauthorized", "message": "Invalid or expired access token"},
                status_code=401
            )

        # Try Basic auth (client_id:client_secret)
        if auth_header.startswith("Basic ") and has_oauth:
            try:
                encoded = auth_header[6:]
                decoded = base64.b64decode(encoded).decode("utf-8")
                client_id, client_secret = decoded.split(":", 1)
                if client_id == settings.oauth_client_id and client_secret == settings.oauth_client_secret:
                    return await call_next(request)
            except Exception:
                pass
            return JSONResponse(
                {"error": "Unauthorized", "message": "Invalid client credentials"},
                status_code=401
            )

        # Try API key
        if has_api_key:
            # Check header first
            api_key = request.headers.get("X-API-Key")

            # Then check URL path: /mcp/calendar/key/{api_key}/...
            if not api_key and "/key/" in request.url.path:
                path_parts = request.url.path.split("/key/")
                if len(path_parts) > 1:
                    key_and_rest = path_parts[1].split("/", 1)
                    api_key = key_and_rest[0]

            # Then check query parameter: ?api_key=xxx
            if not api_key:
                api_key = request.query_params.get("api_key")

            if api_key == settings.api_key:
                return await call_next(request)

        return JSONResponse(
            {"error": "Unauthorized", "message": "Invalid or missing authentication"},
            status_code=401
        )

    # Health check endpoints
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "transport": "http", "service": "google-calendar-mcp"}

    @app.get("/mcp/calendar/health")
    async def calendar_health_check():
        return {"status": "ok", "transport": "http", "service": "google-calendar-mcp"}

    # Mount MCP app under /mcp/calendar
    app.mount("/mcp/calendar", mcp_app)

    return app


def serve():
    """Run MCP server with configured transport."""
    from google_calendar.settings import settings

    if settings.transport_mode == "http":
        import uvicorn

        app = create_http_app()
        uvicorn.run(
            app,
            host=settings.http_host,
            port=settings.http_port,
            log_level="info"
        )
    else:
        mcp.run()


if __name__ == "__main__":
    serve()
