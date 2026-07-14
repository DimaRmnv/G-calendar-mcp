"""
OAuth callback server for cloud deployment.

Provides web-based OAuth flow for headless server environments.
Endpoints:
- GET /oauth/start/{account} - Generate OAuth authorization URL
- GET /oauth/callback - Handle OAuth callback from Google
- GET /oauth/status/{account} - Check authorization status
"""

import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow

from google_calendar.api.client import (
    SCOPES,
    clear_service_cache,
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

oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])


def _cleanup_expired_flows() -> int:
    """Remove expired pending flows. Returns count of removed entries."""
    cleanup_expired_flows()
    return 0  # Count not tracked in shared module


@oauth_router.get("/start/{account}")
async def start_oauth(
    account: str,
    email_hint: Optional[str] = Query(None, description="Email to pre-select in Google account chooser")
):
    """
    Generate OAuth authorization URL for account.
    """
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

    if email_hint is None and account_info.get("email"):
        email_hint = account_info["email"]

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

    # Redirect to Google OAuth directly
    return RedirectResponse(url=auth_url, status_code=302)


@oauth_router.get("/callback")
async def oauth_callback(
    code: str = Query(None, description="Authorization code from Google"),
    state: str = Query(None, description="State token for CSRF protection"),
    error: str = Query(None, description="Error from Google if authorization failed")
):
    """
    Handle OAuth callback from Google.
    """
    if error:
        return HTMLResponse(
            f"""
            <!DOCTYPE html>
            <html>
            <head><title>Authorization Failed</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
                <h1>Authorization Failed</h1>
                <p style="color: #dc3545;">{error}</p>
                <p>Please try again or check your Google account settings.</p>
            </body>
            </html>
            """,
            status_code=400
        )

    pending_data = get_pending_flow_data(state) if state else None
    if not state or not pending_data:
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html>
            <head><title>Invalid Request</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
                <h1>Invalid or Expired Request</h1>
                <p>The authorization session has expired or is invalid.</p>
                <p>Please start the authorization process again.</p>
            </body>
            </html>
            """,
            status_code=400
        )

    # Check if flow has expired (TTL validation)
    if time.time() - pending_data.get("created_at", 0) > PENDING_FLOW_TTL_SECONDS:
        get_pending_flow(state)  # Remove expired flow
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html>
            <head><title>Session Expired</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
                <h1>Session Expired</h1>
                <p>Your authorization session has expired (15 minute limit).</p>
                <p>Please start the authorization process again.</p>
            </body>
            </html>
            """,
            status_code=400
        )

    if not code:
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html>
            <head><title>Missing Code</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
                <h1>Missing Authorization Code</h1>
                <p>No authorization code was provided by Google.</p>
            </body>
            </html>
            """,
            status_code=400
        )

    pending = get_pending_flow(state)
    flow = pending["flow"]
    account = pending["account"]

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        save_credentials(account, creds)
        clear_service_cache(account)  # Clear cached service to use new credentials

        return HTMLResponse(
            f"""
            <!DOCTYPE html>
            <html>
            <head><title>Authorization Successful</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
                <h1 style="color: #28a745;">Authorization Successful!</h1>
                <p>Account <strong>'{account}'</strong> has been authorized for Google Calendar.</p>
                <p>You can close this window and return to your application.</p>
            </body>
            </html>
            """
        )
    except Exception as e:
        return HTMLResponse(
            f"""
            <!DOCTYPE html>
            <html>
            <head><title>Authorization Failed</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center;">
                <h1 style="color: #dc3545;">Authorization Failed</h1>
                <p>Error: {str(e)}</p>
                <p>Please try again.</p>
            </body>
            </html>
            """,
            status_code=500
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
