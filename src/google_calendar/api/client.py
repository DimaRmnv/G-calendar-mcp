"""
Google Calendar API client — OAuth and service management.

Handles:
- OAuth 2.0 authentication flow
- Token storage and refresh
- Calendar service instance creation
- Token expiration handling for cloud deployment
- Auto-reauth with auth_url on token errors
"""

import http.client
import json
import os
import logging
import time
import inspect
from functools import wraps
from typing import Optional, Callable
from pathlib import Path

import httplib2
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError, TransportError
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

def _generate_google_oauth_url(account: str) -> Optional[str]:
    """
    Generate Google OAuth authorization URL directly.

    Returns the Google OAuth URL that user can click to authorize.
    Also stores the pending flow state for callback handling.
    Returns None if OAuth is not configured or limit reached.
    """
    try:
        from google_auth_oauthlib.flow import Flow
        from google_calendar.oauth_state import generate_state, store_pending_flow

        oauth_client = load_oauth_client()
        if not oauth_client:
            return None

        if not settings.oauth_redirect_uri:
            return None

        account_info = get_account(account)
        email_hint = account_info.get("email") if account_info else None

        flow = Flow.from_client_config(
            oauth_client,
            scopes=SCOPES,
            redirect_uri=settings.oauth_redirect_uri
        )

        state = generate_state()

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="false",
            prompt="consent",
            state=state,
            login_hint=email_hint
        )

        # Store pending flow for callback
        if not store_pending_flow(state, account, flow, email_hint):
            logger.warning(f"Too many pending OAuth flows, cannot start new one for '{account}'")
            return None

        return auth_url
    except Exception as e:
        logger.error(f"Failed to generate OAuth URL for '{account}': {e}")
        return None


def handle_auth_errors(func: Callable) -> Callable:
    """
    Decorator to catch auth errors and return them as structured dict.

    Handles:
    - AuthRequiredError, TokenExpiredError (our custom exceptions)
    - RefreshError (from google-auth library when token refresh fails)

    Returns dict with auth_url pointing to /oauth/start/{account}
    """
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except (AuthRequiredError, TokenExpiredError) as e:
                logger.warning(f"Auth error in {func.__name__}: {e}")
                return e.to_dict()
            except RefreshError as e:
                # Token refresh failed during API call (from google-auth library)
                account = kwargs.get('account') or get_default_account() or "default"
                logger.warning(f"RefreshError in {func.__name__} for '{account}': {e}")
                auth_url = settings.get_auth_start_url(account)
                return {
                    "error": "auth_required",
                    "message": f"Token refresh failed for '{account}'. Authorize here: {auth_url}",
                    "auth_url": auth_url,
                    "account": account,
                }
        return async_wrapper
    else:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (AuthRequiredError, TokenExpiredError) as e:
                logger.warning(f"Auth error in {func.__name__}: {e}")
                return e.to_dict()
            except RefreshError as e:
                # Token refresh failed during API call (from google-auth library)
                account = kwargs.get('account') or get_default_account() or "default"
                logger.warning(f"RefreshError in {func.__name__} for '{account}': {e}")
                auth_url = settings.get_auth_start_url(account)
                return {
                    "error": "auth_required",
                    "message": f"Token refresh failed for '{account}'. Authorize here: {auth_url}",
                    "auth_url": auth_url,
                    "account": account,
                }
        return wrapper


# ============================================================================
# API Request Helper with Retry and Auth Error Handling
# ============================================================================

# 403 reasons meaning "slow down": Google refused before running the request, so
# repeating it is safe for every method.
_RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
# 403 reasons a new authorization fixes (token lacks a scope).
_AUTH_REASONS = {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}
# Transport failures: the request may or may not have reached Google.
_TRANSPORT_ERRORS = (OSError, httplib2.HttpLib2Error, http.client.HTTPException)


def _error_reasons(error: HttpError) -> set[str]:
    """Reason codes of a Google error body: `error.errors[].reason` and `error.details[].reason`.

    Tolerates any body shape: a malformed one yields no reasons, so the HttpError itself
    still reaches the caller.
    """
    try:
        body = json.loads(error.content.decode("utf-8"))
    except (ValueError, AttributeError):
        return set()
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return set()
    items = [
        item
        for key in ("errors", "details")
        if isinstance(err.get(key), list)
        for item in err[key]
    ]
    return {
        item["reason"] for item in items
        if isinstance(item, dict) and isinstance(item.get("reason"), str)
    }


def execute_with_retry(request, account: Optional[str], *, idempotent: bool = True, max_attempts: int = 3):
    """
    Execute a Google API request — the single executor for every Calendar call.

    - 401, or 403 for a missing scope → AuthRequiredError carrying auth_url.
    - 429 or 403 rate limit → retried with backoff for any method (Google refused it).
    - 5xx and transport errors → retried only when `idempotent`: a create or move whose
      response was lost may already have happened, and repeating it duplicates the event.
    - A transport error while refreshing the token → retried for any method.
    - Any other HttpError (403 not the organizer, 404, 400) → raised unchanged.

    Raises:
        AuthRequiredError, RateLimitError, HttpError, or the transport error.
    """
    account = account or get_default_account() or "default"

    for attempt in range(1, max_attempts + 1):
        last = attempt == max_attempts
        try:
            return request.execute()

        except HttpError as e:
            status = e.resp.status
            reasons = _error_reasons(e)
            logger.warning(
                "Calendar API error %s %s for account '%s' (attempt %d/%d)",
                status, sorted(reasons), account, attempt, max_attempts,
            )

            if status == 401 or (status == 403 and reasons & _AUTH_REASONS):
                clear_service_cache(account)
                raise AuthRequiredError(
                    account=account,
                    auth_url=settings.get_auth_start_url(account),
                    reason=f"Google refused the credentials ({status} {', '.join(sorted(reasons)) or 'no reason'})",
                ) from e

            if status == 429 or (status == 403 and reasons & _RATE_LIMIT_REASONS):
                if last:
                    raise RateLimitError(
                        f"Google rate limit for account '{account}' persisted after {max_attempts} attempts"
                    ) from e
                time.sleep(2 ** attempt)
                continue

            if status >= 500 and idempotent and not last:
                time.sleep(2 ** (attempt - 1))
                continue

            raise

        except RefreshError as e:
            clear_service_cache(account)
            logger.error("Token refresh failed for account '%s': %s", account, e)
            raise AuthRequiredError(
                account=account,
                auth_url=settings.get_auth_start_url(account),
                reason=f"Token refresh failed: {str(e)[:200]}",
            ) from e

        except TransportError as e:
            # google-auth raises this only while refreshing the token — before the API
            # request is sent, or after Google refused it with 401 — so nothing ran yet.
            logger.warning(
                "Token refresh transport error for account '%s' (attempt %d/%d): %r",
                account, attempt, max_attempts, e,
            )
            if not last:
                time.sleep(2 ** (attempt - 1))
                continue
            raise

        except _TRANSPORT_ERRORS as e:
            logger.warning(
                "Calendar API transport error for account '%s' (attempt %d/%d, idempotent=%s): %r",
                account, attempt, max_attempts, idempotent, e,
            )
            if idempotent and not last:
                time.sleep(2 ** (attempt - 1))
                continue
            raise

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
    Raises ValueError when Google rejects the calls; an authorization problem
    propagates as AuthRequiredError so the caller can answer with auth_url.
    """
    service = get_service(account)

    try:
        setting = execute_with_retry(service.settings().get(setting="timezone"), account)
        calendar = execute_with_retry(service.calendars().get(calendarId="primary"), account)
    except HttpError as e:
        raise ValueError(f"Failed to verify credentials: {e}") from e

    return {
        "email": calendar.get("id"),  # Primary calendar ID is the email
        "timezone": setting.get("value"),
        "calendar_name": calendar.get("summary"),
    }


def get_authorized_email(account: str) -> Optional[str]:
    """
    Get email address for authorized account.

    Returns None if Google rejects the lookup; authorization errors propagate.
    """
    try:
        return verify_credentials(account).get("email")
    except ValueError:
        return None


def get_user_timezone(account: Optional[str] = None) -> str:
    """
    Get user's timezone from Calendar settings (IANA, e.g. 'Asia/Bangkok').

    Errors propagate: naive times are interpreted in this zone, so a silent fallback
    to UTC would shift every requested window.
    """
    service = get_service(account)
    setting = execute_with_retry(service.settings().get(setting="timezone"), account)
    return setting["value"]
