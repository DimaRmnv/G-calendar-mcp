"""
OAuth callback server for cloud deployment.

Provides web-based OAuth flow for headless server environments.
Endpoints:
- GET /oauth/start/{account} - Generate OAuth authorization URL
- GET /oauth/callback - Handle OAuth callback from Google
- GET /oauth/status/{account} - Check authorization status
"""

import secrets
import hashlib
import time
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, Form
from fastapi.responses import HTMLResponse

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from google_calendar.settings import settings
from google_calendar.utils.config import load_oauth_client, get_account
from google_calendar.api.client import SCOPES, save_credentials, get_credentials


oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])

# In-memory state store for pending OAuth flows
_pending_flows: dict[str, dict] = {}

# In-memory token store for OAuth 2.0 Client Credentials
_active_tokens: dict[str, float] = {}

# Token lifetime: 1 hour
TOKEN_LIFETIME_SECONDS = 3600


def generate_access_token(client_id: str) -> str:
    """Generate a secure access token."""
    random_part = secrets.token_urlsafe(32)
    timestamp = str(int(time.time()))
    token_input = f"{client_id}:{random_part}:{timestamp}"
    return hashlib.sha256(token_input.encode()).hexdigest()


def validate_access_token(token: str) -> bool:
    """Check if access token is valid and not expired."""
    if token not in _active_tokens:
        return False
    expiry = _active_tokens[token]
    if time.time() > expiry:
        del _active_tokens[token]
        return False
    return True


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

    state = secrets.token_urlsafe(32)

    if email_hint is None and account_info.get("email"):
        email_hint = account_info["email"]

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
        state=state,
        login_hint=email_hint
    )

    _pending_flows[state] = {
        "account": account,
        "flow": flow,
        "email_hint": email_hint
    }

    return {
        "auth_url": auth_url,
        "state": state,
        "account": account,
        "message": f"Open this URL to authorize account '{account}': {auth_url}"
    }


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

    if not state or state not in _pending_flows:
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

    pending = _pending_flows.pop(state)
    flow = pending["flow"]
    account = pending["account"]

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        save_credentials(account, creds)

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


@oauth_router.post("/token")
async def get_token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...)
):
    """
    OAuth 2.0 Token endpoint for Client Credentials flow.
    """
    if grant_type != "client_credentials":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_grant_type",
                "error_description": "Only client_credentials grant type is supported"
            }
        )

    if not settings.oauth_client_id or not settings.oauth_client_secret:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "server_error",
                "error_description": "OAuth client credentials not configured on server"
            }
        )

    if client_id != settings.oauth_client_id or client_secret != settings.oauth_client_secret:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_client",
                "error_description": "Invalid client_id or client_secret"
            }
        )

    access_token = generate_access_token(client_id)
    expiry_time = time.time() + TOKEN_LIFETIME_SECONDS
    _active_tokens[access_token] = expiry_time

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": TOKEN_LIFETIME_SECONDS
    }
