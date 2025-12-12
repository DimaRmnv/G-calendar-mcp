"""
Google Calendar API client — OAuth and service management.

Handles:
- OAuth 2.0 authentication flow
- Token storage and refresh
- Calendar service instance creation
"""

import json
import os
import logging
from typing import Optional
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

from gcalendar_mcp.utils.config import (
    get_token_path,
    get_oauth_client_path,
    load_oauth_client,
    get_account,
    get_default_account,
)


# OAuth scopes required for full Calendar access
SCOPES = [
    "https://www.googleapis.com/auth/calendar",           # Full access to calendars
    "https://www.googleapis.com/auth/calendar.events",    # Manage events
    "https://www.googleapis.com/auth/calendar.settings.readonly",  # Read settings (timezone)
]


logger = logging.getLogger(__name__)


# Cache for service instances
_services: dict[str, Resource] = {}


def get_credentials(account: str) -> Optional[Credentials]:
    """
    Get valid credentials for account.
    
    Loads from token file, refreshes if expired.
    Returns None if no valid credentials available.
    """
    token_path = get_token_path(account)
    
    if not token_path.exists():
        return None
    
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except (json.JSONDecodeError, ValueError):
        return None
    
    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed token with secure permissions
            token_path.write_text(creds.to_json(), encoding="utf-8")
            os.chmod(token_path, 0o600)
        except Exception as e:
            logger.warning(f"Token refresh failed for account '{account}': {e}")
            return None
    
    if creds and creds.valid:
        return creds
    
    return None


def save_credentials(account: str, creds: Credentials) -> None:
    """Save credentials to token file with secure permissions."""
    token_path = get_token_path(account)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token_path, 0o600)


def run_oauth_flow(account: str, email_hint: Optional[str] = None) -> Credentials:
    """
    Run OAuth flow for account.
    
    Opens browser for user authorization.
    Args:
        account: Account name for storage
        email_hint: Email to pre-select in Google's account chooser
    Returns credentials on success.
    Raises ValueError if OAuth client not configured.
    """
    oauth_client = load_oauth_client()
    
    if not oauth_client:
        raise ValueError(
            "OAuth client not configured. "
            "Run 'gcalendar-mcp auth' and paste your Google Cloud credentials."
        )
    
    oauth_path = get_oauth_client_path()
    
    flow = InstalledAppFlow.from_client_secrets_file(
        str(oauth_path),
        SCOPES
    )
    
    # Build authorization URL with login_hint
    auth_url, _ = flow.authorization_url(
        prompt="consent",  # Force consent screen to allow account selection
        login_hint=email_hint  # Pre-select this email in account chooser
    )
    
    # Run local server for OAuth callback
    creds = flow.run_local_server(
        port=0,
        authorization_prompt_message=f"Authorize GCalendar MCP for '{account}' ({email_hint or 'select account'}) in browser...",
        success_message="Authorization complete. You can close this window.",
    )
    
    # Save credentials
    save_credentials(account, creds)
    
    return creds


def get_service(account: Optional[str] = None) -> Resource:
    """
    Get Calendar API service for account.
    
    Uses default account if not specified.
    Caches service instances for reuse.
    
    Raises:
        ValueError: If account not found or not authorized.
    """
    # Resolve account name
    if account is None:
        account = get_default_account()
    
    if account is None:
        raise ValueError(
            "No account specified and no default account configured. "
            "Run 'gcalendar-mcp auth' to add an account."
        )
    
    # Check account exists
    account_info = get_account(account)
    if account_info is None:
        raise ValueError(
            f"Account '{account}' not found. "
            f"Run 'gcalendar-mcp auth' to add it."
        )
    
    # Return cached service if available
    if account in _services:
        return _services[account]
    
    # Get credentials
    creds = get_credentials(account)
    
    if creds is None:
        raise ValueError(
            f"Account '{account}' not authorized. "
            f"Run 'gcalendar-mcp auth' to authorize."
        )
    
    # Build service
    service = build("calendar", "v3", credentials=creds)
    
    # Cache for reuse
    _services[account] = service
    
    return service


def clear_service_cache(account: Optional[str] = None) -> None:
    """
    Clear cached service instances.
    
    If account specified, clears only that account.
    Otherwise clears all cached services.
    """
    global _services
    
    if account:
        _services.pop(account, None)
    else:
        _services = {}


def verify_credentials(account: str) -> dict:
    """
    Verify credentials by fetching calendar settings.
    
    Returns profile info on success.
    Raises ValueError on failure.
    """
    service = get_service(account)
    
    try:
        # Get user's timezone setting
        settings = service.settings().get(setting="timezone").execute()
        timezone = settings.get("value")
        
        # Get primary calendar info
        calendar = service.calendars().get(calendarId="primary").execute()
        
        return {
            "email": calendar.get("id"),  # Primary calendar ID is the email
            "timezone": timezone,
            "calendar_name": calendar.get("summary"),
        }
    except Exception as e:
        raise ValueError(f"Failed to verify credentials: {e}")


def get_authorized_email(account: str) -> Optional[str]:
    """
    Get email address for authorized account.
    
    Returns None if account not authorized.
    """
    try:
        profile = verify_credentials(account)
        return profile.get("email")
    except (ValueError, Exception):
        return None


def get_user_timezone(account: Optional[str] = None) -> Optional[str]:
    """
    Get user's timezone from Calendar settings.
    
    Returns IANA timezone string (e.g., 'Asia/Bangkok') or None.
    """
    try:
        service = get_service(account)
        settings = service.settings().get(setting="timezone").execute()
        return settings.get("value")
    except Exception:
        return None
