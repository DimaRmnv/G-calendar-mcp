"""
GCalendar MCP Server.

FastMCP server exposing Google Calendar tools for Claude Desktop.
Supports both stdio (local) and HTTP (cloud) transport modes.

Tools (7 total):
- calendars: Calendar management, colors, settings, accounts
- availability: Check freebusy, find meeting slots
- events: List, create, get, update, delete, search, batch
- attendees: Manage attendees, respond to invitations
- weekly_brief: Weekly schedule overview
- projects: Project management (phases, tasks, norms, reports)
- contacts: Contact management (channels, assignments)
"""

from fastmcp import FastMCP

# Unified tools (consolidated from 16 to 7)
from google_calendar.tools.calendars import calendars
from google_calendar.tools.availability import availability
from google_calendar.tools.events import events
from google_calendar.tools.attendees import attendees
from google_calendar.tools.intelligence import weekly_brief
from google_calendar.tools.projects import projects
from google_calendar.tools.contacts import contacts


# Create server
mcp = FastMCP(
    name="google-calendar",
    instructions="""Google Calendar integration. Multi-account support.

ACCOUNT SELECTION:
When user mentions calendar name ("личный", "personal", "рабочий", "work", etc.):
1. Call calendars(action="list_accounts") to get available accounts
2. Match user's description to account name
3. Use account="<matched_name>" in subsequent calls

ACCOUNTS vs CALENDARS:
- ACCOUNTS = different Google accounts (work, personal). Parameter: account="work"
- CALENDARS = calendars within one account (primary, holidays). Parameter: calendar_id="primary"

TOOLS (7):
- calendars: Manage calendars, colors, settings, accounts
  Actions: list, get, create, update, delete, colors, settings, set_timezone, list_accounts

- availability: Check availability and find meeting slots
  Actions: query (freebusy), find_slots (with timezone support)

- events: All event operations
  Actions: list, create, get, update, delete, search, batch
  For recurring: scope="single"|"all"
  For move: destination_calendar_id=...

- attendees: Manage attendees and respond to invitations
  Actions: list, add, remove, resend, respond

- weekly_brief: Weekly schedule overview

- projects: Project management (v2 schema)
  Operations: project_*, phase_*, task_*, norm_*, exclusion_*, config_*, report_*
  Organizations: org_*, project_org_* (M:N with projects)
  Hierarchy: PROJECT → PHASE → TASK (tasks linked to phases, not projects)

- contacts: Contact management (v2 schema)
  organization_id links to organizations table
  Relationship tracking: context, relationship_type, relationship_strength

TIME FORMAT: '2024-12-15T10:00:00' (timed) or '2024-12-15' (all-day)"""
)

# Register all 7 tools (fastmcp 1.0 requires calling the decorator)
mcp.tool()(calendars)
mcp.tool()(availability)
mcp.tool()(events)
mcp.tool()(attendees)
mcp.tool()(weekly_brief)
mcp.tool()(projects)
mcp.tool()(contacts)


def create_http_app():
    """
    Create FastAPI app for HTTP transport mode.

    Includes:
    - OAuth callback endpoints
    - API key authentication middleware
    - MCP endpoints
    - TokenExpiredError/AuthRequiredError handling with auth_url
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    from google_calendar.settings import settings
    from google_calendar.oauth_server import oauth_router, validate_access_token
    from google_calendar.export_router import export_router
    from google_calendar.api.client import TokenExpiredError, AuthRequiredError, RateLimitError

    # Get MCP app first to access its lifespan
    mcp_app = mcp.http_app()

    app = FastAPI(
        title="Google Calendar MCP",
        description="MCP server for Google Calendar integration",
        version="0.2.0",
        lifespan=mcp_app.lifespan  # Required for FastMCP session management
    )

    # =========================================================================
    # Exception handlers for auto-reauth
    # =========================================================================

    @app.exception_handler(TokenExpiredError)
    async def token_expired_handler(request: Request, exc: TokenExpiredError):
        """Return structured JSON with auth_url for token expiration."""
        return JSONResponse(
            status_code=401,
            content=exc.to_dict()
        )

    @app.exception_handler(AuthRequiredError)
    async def auth_required_handler(request: Request, exc: AuthRequiredError):
        """Return structured JSON with auth_url for auth failures."""
        return JSONResponse(
            status_code=401,
            content=exc.to_dict()
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request: Request, exc: RateLimitError):
        """Return 429 for rate limit errors."""
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limit", "message": str(exc)}
        )

    # Add export router (no auth - UUID is the token)
    app.include_router(export_router)

    # Add OAuth router under /mcp/calendar/oauth
    app.include_router(oauth_router, prefix="/mcp/calendar")

    # Authentication middleware
    @app.middleware("http")
    async def check_auth(request: Request, call_next):
        import base64

        # Skip auth check for OAuth endpoints
        if "/oauth" in request.url.path:
            return await call_next(request)

        # Skip for export downloads (UUID is the token)
        if request.url.path.startswith("/export/"):
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
