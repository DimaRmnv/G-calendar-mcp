"""
Google OAuth endpoints for the cloud deployment (headless server).

Endpoints (mounted under /mcp/calendar):
- GET /oauth/start/{account}?token=… — public, but only for a link the server minted
  (oauth_links); redirects to Google consent
- GET /oauth/callback — public; stores the token only when the Google identity that
  consented is the one configured for the account
- GET /oauth/status/{account}, GET /oauth/accounts — behind the server's authentication
"""

import html
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from google_calendar import oauth_links
from google_calendar.api.client import (
    SCOPES,
    clear_service_cache,
    execute_with_retry,
    get_credentials,
    save_credentials,
)
from google_calendar.oauth_state import (
    PENDING_FLOW_TTL_SECONDS,
    cleanup_expired_flows,
    generate_state,
    get_pending_flow,
    get_pending_flow_data,
    store_pending_flow,
)
from google_calendar.settings import settings
from google_calendar.utils.config import get_account, load_oauth_client

logger = logging.getLogger(__name__)

oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])

# The pages show server text and escaped values only: nothing may load, run or frame them,
# and the callback URL (code, state) must not leak through a Referer.
_PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
_RED, _GREEN = "#dc3545", "#28a745"


def _page(title: str, lines: list[str], status_code: int = 200, color: Optional[str] = None) -> HTMLResponse:
    """A minimal HTML page; the title and every line are HTML-escaped."""
    heading_style = f' style="color: {color};"' if color else ""
    body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    return HTMLResponse(
        "<!DOCTYPE html><html><head>"
        f"<title>{html.escape(title)}</title></head>"
        '<body style="font-family: system-ui; padding: 40px; text-align: center;">'
        f"<h1{heading_style}>{html.escape(title)}</h1>{body}</body></html>",
        status_code=status_code,
        headers=_PAGE_HEADERS,
    )


def _cleanup_expired_flows() -> int:
    """Remove expired pending flows. Returns count of removed entries."""
    cleanup_expired_flows()
    return 0  # Count not tracked in shared module


def _exchange_code(flow: Flow, code: str):
    """Exchange the authorization code for credentials."""
    flow.fetch_token(code=code)
    return flow.credentials


def _consenting_email(creds, account: str) -> str:
    """E-mail of the Google identity behind `creds`: the id of its primary calendar."""
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return execute_with_retry(service.calendars().get(calendarId="primary"), account)["id"]


@oauth_router.get("/start/{account}")
async def start_oauth(
    account: str,
    token: Optional[str] = Query(None, description="Signed link token minted by the server"),
):
    """
    Redirect to Google consent for account — only for a link the server minted.
    """
    # Checked before the account is looked up, so a refusal does not reveal whether it exists.
    if not (oauth_links.start_is_open() or oauth_links.verify(token, account)):
        logger.warning("OAuth start refused for account %r: missing, invalid or expired link", account)
        raise HTTPException(
            status_code=403,
            detail="This authorization link is invalid or has expired. Ask the assistant for a new one.",
        )

    account_info = get_account(account)
    if account_info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account}' not found. Add it first with CLI."
        )

    oauth_client = load_oauth_client()
    if not oauth_client:
        raise HTTPException(
            status_code=500,
            detail="OAuth client not configured. Place oauth_client.json in data directory."
        )

    if not settings.oauth_redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="GCAL_MCP_OAUTH_REDIRECT_URI not configured"
        )

    flow = Flow.from_client_config(
        oauth_client,
        scopes=SCOPES,
        redirect_uri=settings.oauth_redirect_uri
    )

    state = generate_state()
    email_hint = account_info.get("email")

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
        state=state,
        login_hint=email_hint
    )

    # Store pending flow (handles cleanup and limit check)
    if not store_pending_flow(state, account, flow, email_hint):
        raise HTTPException(
            status_code=503,
            detail="Too many pending OAuth flows. Please try again later."
        )

    return RedirectResponse(url=auth_url, status_code=302)


@oauth_router.get("/callback")
async def oauth_callback(
    code: str = Query(None, description="Authorization code from Google"),
    state: str = Query(None, description="State token for CSRF protection"),
    error: str = Query(None, description="Error from Google if authorization failed")
):
    """
    Handle OAuth callback from Google: store the token for the account the flow was
    started for, if the consenting Google identity is the account's configured one.
    """
    if error:
        return _page(
            "Authorization Failed",
            [f"Google reported: {error}", "Please try again or check your Google account settings."],
            400, _RED,
        )

    pending_data = get_pending_flow_data(state) if state else None
    if not state or not pending_data:
        return _page(
            "Invalid or Expired Request",
            ["The authorization session has expired or is invalid.",
             "Please start the authorization process again."],
            400,
        )

    if time.time() - pending_data.get("created_at", 0) > PENDING_FLOW_TTL_SECONDS:
        get_pending_flow(state)  # Remove expired flow
        return _page(
            "Session Expired",
            ["Your authorization session has expired (15 minute limit).",
             "Please start the authorization process again."],
            400,
        )

    if not code:
        return _page("Missing Authorization Code", ["No authorization code was provided by Google."], 400)

    pending = get_pending_flow(state)  # consumes the state: one callback per started flow
    flow = pending["flow"]
    account = pending["account"]
    expected = ((get_account(account) or {}).get("email") or "").lower()

    try:
        creds = _exchange_code(flow, code)
        consented = _consenting_email(creds, account).lower()
    except Exception:
        # Browser-page boundary: nothing is stored yet; the cause goes to the log, not the page.
        logger.exception("OAuth code exchange failed for account %s", account)
        return _page("Authorization Failed", ["Google did not complete the authorization. Please start again."], 500, _RED)

    if not expected or consented != expected:
        logger.warning("OAuth consent for account %s refused: a different Google identity signed in", account)
        return _page(
            "Wrong Google Account",
            [f"Account '{account}' is set up for a different Google account.",
             "Sign in with that account and start again."],
            403, _RED,
        )

    save_credentials(account, creds)
    clear_service_cache(account)  # Clear cached service to use new credentials
    return _page(
        "Authorization Successful!",
        [f"Account '{account}' has been authorized for Google Calendar.",
         "You can close this window and return to your application."],
        200, _GREEN,
    )


@oauth_router.get("/status/{account}")
async def oauth_status(account: str):
    """
    Check authorization status for account.
    """
    account_info = get_account(account)
    if account_info is None:
        return {
            "status": "not_found",
            "account": account,
            "message": f"Account '{account}' not found"
        }

    try:
        creds = get_credentials(account)
    except Exception:
        creds = None

    if creds and creds.valid:
        return {
            "status": "authorized",
            "account": account,
            "email": account_info.get("email"),
            "message": "Account is authorized and token is valid"
        }
    elif creds and creds.expired:
        auth_url = settings.get_auth_start_url(account)
        return {
            "status": "expired",
            "account": account,
            "email": account_info.get("email"),
            "auth_url": auth_url,
            "message": "Token expired, re-authorization required"
        }
    else:
        auth_url = settings.get_auth_start_url(account)
        return {
            "status": "not_authorized",
            "account": account,
            "email": account_info.get("email"),
            "auth_url": auth_url,
            "message": "Account not authorized, authorization required"
        }


@oauth_router.get("/accounts")
async def list_oauth_accounts():
    """
    List all accounts and their authorization status.
    """
    from google_calendar.utils.config import list_accounts as get_all_accounts

    accounts = get_all_accounts()
    result = []

    for name, info in accounts.items():
        try:
            creds = get_credentials(name)
            if creds and creds.valid:
                status = "authorized"
            elif creds and creds.expired:
                status = "expired"
            else:
                status = "not_authorized"
        except Exception:
            status = "error"

        result.append({
            "account": name,
            "email": info.get("email"),
            "status": status,
            "auth_url": settings.get_auth_start_url(name)
        })

    return {"accounts": result}
