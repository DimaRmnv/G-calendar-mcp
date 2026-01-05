"""
Google Calendar API client — OAuth and service management.

Handles:
- OAuth 2.0 authentication flow
- Token storage and refresh
- Calendar service instance creation
- Token expiration handling for cloud deployment
- Auto-reauth with auth_url on token errors
"""

import json
import os
import logging
import time
import inspect
from functools import wraps
from typing import Optional, Callable
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from google_calendar.settings import settings
from google_calendar.utils.config import (
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


# ============================================================================
# Custom Exception Classes for Auto-Reauth
# ============================================================================

class TokenExpiredError(Exception):
    """
    Token expired and needs re-authorization.

    Raised when token refresh fails and user needs to re-authorize.
    Contains auth_url for web-based re-authorization if available.
    """

    def __init__(self, account: str, auth_url: Optional[str] = None, message: Optional[str] = None):
        self.account = account
        self.auth_url = auth_url
        self.message = message or f"Token expired for account '{account}'"
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "error": "token_expired",
            "account": self.account,
            "message": self.message,
            "auth_url": self.auth_url,
            "action_required": "Please authorize the account using the provided URL"
        }


class AuthRequiredError(Exception):
    """
    Authorization required - token invalid or revoked.

    Raised when API calls fail due to authentication issues.
    Contains auth_url for user to re-authorize.
    """

    def __init__(self, account: str, auth_url: Optional[str], reason: str):
        self.account = account
        self.auth_url = auth_url
        self.reason = reason
        super().__init__(f"Calendar authorization required for '{account}': {reason}")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "error": "auth_required",
            "message": f"Google Calendar authorization required: {self.reason}",
            "auth_url": self.auth_url,
            "account": self.account,
            "action_required": "Please authorize using the provided URL"
        }


class CalendarAPIError(Exception):
    """Base class for Calendar API errors."""
    pass


class RateLimitError(CalendarAPIError):
    """Rate limit exceeded - retry later."""
    pass


# ============================================================================
# Decorator for MCP Tools
# ============================================================================

def handle_auth_errors(func: Callable) -> Callable:
    """
    Decorator to catch auth errors and return them as structured dict.

    Use on MCP tools to ensure auth errors return auth_url for reauthorization
    instead of raising exceptions that get converted to plain text errors.

    Supports both sync and async functions.

    Returns dict with error info:
        {
            "error": "auth_required",
            "message": "...",
            "auth_url": "https://...",
            "account": "personal"
        }
    """
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except (AuthRequiredError, TokenExpiredError) as e:
                logger.warning(f"Auth error in {func.__name__}: {e}")
                return e.to_dict()
        return async_wrapper
    else:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (AuthRequiredError, TokenExpiredError) as e:
                logger.warning(f"Auth error in {func.__name__}: {e}")
                return e.to_dict()
        return wrapper


# ============================================================================
# API Request Helper with Retry and Auth Error Handling
# ============================================================================

def execute_with_retry(request, account: str, max_retries: int = 3):
    """
    Execute Google API request with retry and error handling.

    Handles:
    - 401/403 with invalid_grant → AuthRequiredError with auth_url
    - 429 rate limit → retry with exponential backoff
    - 5xx server errors → retry
    - Network errors → retry

    Args:
        request: Google API request object (before .execute())
        account: Account name for error context
        max_retries: Maximum retry attempts (default: 3)

    Returns:
        API response dict

    Raises:
        AuthRequiredError: Token invalid/revoked, contains auth_url
        RateLimitError: Rate limit exceeded after retries
        HttpError: Other API errors
    """
    for attempt in range(max_retries):
        try:
            return request.execute()

        except HttpError as e:
            status = e.resp.status
            error_content = e.content.decode("utf-8", errors="ignore") if e.content else ""

            logger.warning(
                f"Calendar API error {status} for account '{account}' "
                f"(attempt {attempt + 1}/{max_retries}): {error_content[:200]}"
            )

            # Auth errors - no retry, need reauth
            if status in (401, 403):
                clear_service_cache(account)
                auth_url = settings.get_auth_start_url(account)

                # Check for specific auth error messages
                if any(msg in error_content.lower() for msg in [
                    "invalid_grant",
                    "token has been",
                    "token expired",
                    "invalid credentials",
                    "request had invalid authentication"
                ]):
                    logger.error(f"Token expired/revoked for account '{account}'")
                    raise AuthRequiredError(
                        account=account,
                        auth_url=auth_url,
                        reason="Token expired or revoked"
                    )

                # Permission denied
                logger.error(f"Permission denied for account '{account}': {error_content[:100]}")
                raise AuthRequiredError(
                    account=account,
                    auth_url=auth_url,
                    reason=f"Permission denied: {error_content[:100]}"
                )

            # Rate limit - retry with backoff
            if status == 429:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.info(f"Rate limited, waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue
                logger.error(f"Rate limit exceeded after {max_retries} retries")
                raise RateLimitError("Rate limit exceeded after retries")

            # Server errors - retry
            if status >= 500:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.info(f"Server error {status}, retrying in {wait}s...")
                    time.sleep(wait)
                    continue

            # Other errors - don't retry
            raise

        except Exception as e:
            # Network errors and other exceptions - retry
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Request failed: {e}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise

    # Should not reach here, but just in case
    raise CalendarAPIError("Request failed after all retries")


# ============================================================================
# Credential Management
# ============================================================================

def get_credentials(account: str) -> Optional[Credentials]:
    """
    Get valid credentials for account.

    Loads from token file, refreshes if expired.
    Returns None if no valid credentials available.
    Raises TokenExpiredError if refresh fails and re-authorization is needed.
    """
    token_path = get_token_path(account)

    if not token_path.exists():
        logger.debug(f"No token file found for account '{account}'")
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load credentials for '{account}': {e}")
        return None

    # Check if refresh token exists
    if creds and not creds.refresh_token:
        logger.warning(f"No refresh token for account '{account}' - reauth required")
        return None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        logger.info(f"Token expired for account '{account}', attempting refresh...")
        try:
            creds.refresh(Request())
            # Save refreshed token with secure permissions
            token_path.write_text(creds.to_json(), encoding="utf-8")
            os.chmod(token_path, 0o600)
            logger.info(f"Token refreshed successfully for account '{account}'")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Token refresh failed for '{account}': {error_msg}")

            # Clear cached service
            clear_service_cache(account)
            auth_url = settings.get_auth_start_url(account)

            # Check if it's invalid_grant (token revoked)
            if "invalid_grant" in error_msg.lower():
                raise AuthRequiredError(
                    account=account,
                    auth_url=auth_url,
                    reason="Refresh token revoked or expired"
                )

            raise TokenExpiredError(
                account=account,
                auth_url=auth_url,
                message=f"Token refresh failed for '{account}': {error_msg}"
            )

    if creds and creds.valid:
        return creds

    logger.warning(f"Credentials invalid for account '{account}'")
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
            "Run 'google-calendar-mcp auth' and paste your Google Cloud credentials."
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
        ValueError: If account not found.
        TokenExpiredError: If token expired and needs re-authorization.
    """
    # Resolve account name
    if account is None:
        account = get_default_account()

    if account is None:
        raise ValueError(
            "No account specified and no default account configured. "
            "Run 'google-calendar-mcp auth' to add an account."
        )

    # Check account exists
    account_info = get_account(account)
    if account_info is None:
        raise ValueError(
            f"Account '{account}' not found. "
            f"Run 'google-calendar-mcp auth' to add it."
        )

    # Return cached service if available
    if account in _services:
        return _services[account]

    # Get credentials (may raise TokenExpiredError)
    creds = get_credentials(account)

    if creds is None:
        auth_url = settings.get_auth_start_url(account)
        raise TokenExpiredError(
            account=account,
            auth_url=auth_url,
            message=f"Account '{account}' not authorized."
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
