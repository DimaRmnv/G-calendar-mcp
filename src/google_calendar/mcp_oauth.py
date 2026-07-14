"""
OAuth 2.1 Authorization Server + Protected Resource for MCP clients.

Background
----------
As of mid-2026 Claude's custom-connector flow performs OAuth 2.1 Dynamic Client
Registration against every remote MCP server on connect — even servers that
authenticate with a plain API key — and there is no "no auth" option in the UI.
Servers that advertise no OAuth metadata fail registration with
"Couldn't register with <name>'s sign-in service". This module turns the server
into a spec-compliant OAuth 2.1 Authorization Server + Protected Resource so that
flow succeeds. Existing API-key authentication keeps working unchanged for other
clients (the auth middleware accepts either an API key or an OAuth bearer token).

Design
------
* Stateless, JWT-based (HS256). Access tokens, refresh tokens and authorization
  codes are signed JWTs, so they survive container restarts (every deploy
  restarts the container) with no database or shared token store.
* The signing key is derived from GCAL_MCP_API_KEY, so no new secret is required
  and rotating the API key invalidates every issued token.
* Authorization Code + PKCE (S256) is the only interactive grant (OAuth 2.1
  forbids the implicit and password grants). The user proves ownership on the
  consent screen by entering the existing API key (constant-time compared).
* refresh_token and (legacy) client_credentials grants are also supported.

Public endpoints (paths are relative to the /mcp/calendar mount, i.e. the public
URL is https://<host>/calendar/mcp/...):
    GET  /.well-known/oauth-protected-resource    RFC 9728 metadata
    GET  /.well-known/oauth-authorization-server  RFC 8414 metadata
    POST /oauth/register                          RFC 7591 dynamic client registration
    GET  /oauth/authorize                          consent screen
    POST /oauth/authorize                          consent submit -> authorization code
    POST /oauth/token                              authorization_code / refresh_token / client_credentials
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import secrets
import time
from base64 import urlsafe_b64encode
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import jwt
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from google_calendar.settings import settings

logger = logging.getLogger(__name__)

# --- Token lifetimes -------------------------------------------------------
ACCESS_TOKEN_TTL = 3600             # 1 hour
REFRESH_TOKEN_TTL = 30 * 24 * 3600  # 30 days
AUTH_CODE_TTL = 60                  # 1 minute (OAuth 2.1: codes must be short-lived)

_ALG = "HS256"

# Domains we redirect authorization codes back to: an exact match or a subdomain
# is allowed. Loopback hosts (Claude Desktop) are matched exactly and handled
# separately (they must not be subdomain-matched). Anything else is rejected to
# prevent open-redirect / authorization-code exfiltration.
_ALLOWED_REDIRECT_DOMAINS = (
    "claude.ai",
    "claude.com",
    "anthropic.com",
)
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")

# Best-effort single-use tracking for authorization codes, as defense in depth on
# top of PKCE. Lost on restart, but codes live only AUTH_CODE_TTL seconds, so the
# restart window is negligible. Assumes a single server instance/worker; scaling
# to multiple workers would require a shared store for this guard.
_consumed_codes: dict[str, float] = {}


class OAuthConfigError(RuntimeError):
    """Server is missing configuration required to act as an OAuth AS."""


# --- Configuration-derived URLs -------------------------------------------

def _base_url() -> str:
    base = settings.server_base_url
    if not base:
        raise OAuthConfigError("GCAL_MCP_SERVER_BASE_URL is not configured")
    return base.rstrip("/")


def issuer() -> str:
    return _base_url()


def resource_url() -> str:
    """The protected resource identifier: the MCP endpoint itself."""
    return f"{_base_url()}/mcp"


def authorization_endpoint() -> str:
    return f"{_base_url()}/oauth/authorize"


def token_endpoint() -> str:
    return f"{_base_url()}/oauth/token"


def registration_endpoint() -> str:
    return f"{_base_url()}/oauth/register"


def protected_resource_metadata_url() -> str:
    return f"{_base_url()}/.well-known/oauth-protected-resource"


def _signing_key() -> bytes:
    if not settings.api_key:
        raise OAuthConfigError("GCAL_MCP_API_KEY is not configured")
    # Domain-separated derivation so the raw API key is never used as a JWT key.
    # NOTE: a leaked access token is an offline oracle for the API key, so
    # GCAL_MCP_API_KEY MUST be high-entropy random (not a human-chosen string).
    return hashlib.sha256(f"mcp-oauth-signing:v1:{settings.api_key}".encode()).digest()


def _now() -> int:
    return int(time.time())


# --- PKCE ------------------------------------------------------------------

def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Validate an S256 PKCE code_verifier against the challenge from /authorize."""
    if not code_verifier or not code_challenge:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(expected, code_challenge)


# --- Token issuance / verification ----------------------------------------

def issue_access_token(subject: str, scope: str = "") -> str:
    payload = {
        "iss": issuer(),
        "aud": resource_url(),
        "sub": subject,
        "typ": "access",
        "scope": scope,
        "iat": _now(),
        "exp": _now() + ACCESS_TOKEN_TTL,
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALG)


def issue_refresh_token(subject: str, scope: str = "") -> str:
    payload = {
        "iss": issuer(),
        "aud": resource_url(),
        "sub": subject,
        "typ": "refresh",
        "scope": scope,
        "iat": _now(),
        "exp": _now() + REFRESH_TOKEN_TTL,
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALG)


def verify_bearer_token(token: str) -> bool:
    """True iff token is a valid, unexpired access token issued by this server."""
    if not token:
        return False
    try:
        claims = jwt.decode(
            token,
            _signing_key(),
            algorithms=[_ALG],
            audience=resource_url(),
            issuer=issuer(),
        )
    except (jwt.InvalidTokenError, OAuthConfigError):
        return False
    return claims.get("typ") == "access"


def _decode_refresh_token(token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            _signing_key(),
            algorithms=[_ALG],
            audience=resource_url(),
            issuer=issuer(),
        )
    except (jwt.InvalidTokenError, OAuthConfigError):
        return None
    return claims if claims.get("typ") == "refresh" else None


# --- Authorization codes ---------------------------------------------------

def _cleanup_consumed_codes() -> None:
    now = time.time()
    for jti, exp in list(_consumed_codes.items()):
        if exp < now:
            _consumed_codes.pop(jti, None)


def issue_auth_code(subject: str, redirect_uri: str, code_challenge: str, scope: str = "") -> str:
    payload = {
        "iss": issuer(),
        "typ": "code",
        "sub": subject,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "scope": scope,
        "iat": _now(),
        "exp": _now() + AUTH_CODE_TTL,
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALG)


def consume_auth_code(
    code: str, redirect_uri: str, code_verifier: str, client_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Validate an authorization code + PKCE verifier; return claims or None.

    Enforces: signature, expiry, exact redirect_uri match, PKCE (S256), single
    use, and — when the client presents a client_id — that it matches the client
    the code was issued to.
    """
    if not code:
        return None
    try:
        claims = jwt.decode(code, _signing_key(), algorithms=[_ALG], issuer=issuer())
    except (jwt.InvalidTokenError, OAuthConfigError):
        return None
    if claims.get("typ") != "code":
        return None
    if claims.get("redirect_uri") != redirect_uri:
        return None
    # Bind the code to its client when one is presented (public clients send it).
    if client_id is not None and claims.get("sub") != client_id:
        return None
    if not verify_pkce(code_verifier, claims.get("code_challenge", "")):
        return None
    jti = claims.get("jti", "")
    _cleanup_consumed_codes()
    if jti in _consumed_codes:
        return None  # replay of an already-redeemed code
    _consumed_codes[jti] = float(claims.get("exp", _now()))
    return claims


# --- Redirect URI validation ----------------------------------------------

def is_allowed_redirect_uri(uri: str) -> bool:
    if not uri:
        return False
    # Reject backslashes and control characters up front: urlparse and the WHATWG
    # (browser) URL parser disagree on them, so "https://evil.com\\@claude.ai"
    # would parse with host=claude.ai here but resolve to evil.com in a browser —
    # an open-redirect / authorization-code exfiltration vector.
    if "\\" in uri or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in uri):
        return False
    try:
        parsed = urlparse(uri)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    # Loopback (Claude Desktop): exact host only (never subdomain-matched).
    if host in _LOOPBACK_HOSTS:
        return parsed.scheme in ("http", "https")
    # Remote: https only, and a real Claude/Anthropic domain or subdomain.
    if parsed.scheme != "https":
        return False
    return any(host == d or host.endswith("." + d) for d in _ALLOWED_REDIRECT_DOMAINS)


# --- Discovery metadata ----------------------------------------------------

def protected_resource_metadata() -> dict[str, Any]:
    return {
        "resource": resource_url(),
        "authorization_servers": [issuer()],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
    }


def authorization_server_metadata() -> dict[str, Any]:
    return {
        "issuer": issuer(),
        "authorization_endpoint": authorization_endpoint(),
        "token_endpoint": token_endpoint(),
        "registration_endpoint": registration_endpoint(),
        "scopes_supported": ["mcp"],
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_post",
            "client_secret_basic",
        ],
        "code_challenge_methods_supported": ["S256"],
    }


def www_authenticate_value(error: Optional[str] = None) -> str:
    """Value for the WWW-Authenticate header on a 401 from the protected resource.

    Points the client at the protected-resource metadata (RFC 9728 §5.1) so it can
    discover the authorization server and start the OAuth flow.
    """
    try:
        parts = [f'resource_metadata="{protected_resource_metadata_url()}"']
    except OAuthConfigError:
        return "Bearer"
    if error:
        parts.append(f'error="{error}"')
    return "Bearer " + ", ".join(parts)


# --- Routers ---------------------------------------------------------------

well_known_router = APIRouter(tags=["oauth-metadata"])
mcp_oauth_router = APIRouter(prefix="/oauth", tags=["oauth-authorization-server"])


def _server_error(exc: OAuthConfigError) -> JSONResponse:
    logger.error("mcp-oauth: not configured: %s", exc)
    return JSONResponse(
        {"error": "server_error", "error_description": str(exc)},
        status_code=500,
    )


@well_known_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata_endpoint():
    try:
        return JSONResponse(protected_resource_metadata())
    except OAuthConfigError as exc:
        return _server_error(exc)


@well_known_router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata_endpoint():
    try:
        return JSONResponse(authorization_server_metadata())
    except OAuthConfigError as exc:
        return _server_error(exc)


@mcp_oauth_router.post("/register")
async def register_client(request: Request):
    """Dynamic Client Registration (RFC 7591). Public client, PKCE required."""
    try:
        _base_url()  # fail fast if unconfigured
    except OAuthConfigError as exc:
        return _server_error(exc)

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    redirect_uris = body.get("redirect_uris") or []
    if not isinstance(redirect_uris, list) or not redirect_uris:
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "redirect_uris is required"},
            status_code=400,
        )
    for uri in redirect_uris:
        if not isinstance(uri, str) or not is_allowed_redirect_uri(uri):
            return JSONResponse(
                {"error": "invalid_redirect_uri", "error_description": f"redirect_uri not allowed: {uri}"},
                status_code=400,
            )

    client_id = secrets.token_urlsafe(16)
    logger.info("mcp-oauth: registered client %s (%s)", client_id, body.get("client_name", "unnamed"))
    response = {
        "client_id": client_id,
        "client_id_issued_at": _now(),
        "redirect_uris": redirect_uris,
        "token_endpoint_auth_method": "none",
        "grant_types": body.get("grant_types") or ["authorization_code", "refresh_token"],
        "response_types": body.get("response_types") or ["code"],
        "scope": body.get("scope", "mcp"),
    }
    if body.get("client_name"):
        response["client_name"] = body["client_name"]
    return JSONResponse(response, status_code=201)


def _error_page(message: str) -> str:
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>Authorization error</title></head>'
        '<body style="font-family:system-ui,sans-serif;padding:40px;text-align:center">'
        f"<h1>Authorization error</h1><p>{html.escape(message)}</p></body></html>"
    )


def _redirect_with_params(redirect_uri: str, params: dict[str, Any]) -> RedirectResponse:
    sep = "&" if urlparse(redirect_uri).query else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)


def _redirect_error(redirect_uri: str, state: Optional[str], error: str, description: str) -> RedirectResponse:
    params = {"error": error, "error_description": description}
    if state:
        params["state"] = state
    return _redirect_with_params(redirect_uri, params)


def _consent_page(params: dict[str, Any], error: str = "") -> HTMLResponse:
    hidden = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in params.items()
        if v is not None
    )
    err_html = f'<p class="err">{html.escape(error)}</p>' if error else ""
    status = 401 if error else 200
    action = html.escape(authorization_endpoint())
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Authorize Google Calendar MCP</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;
       display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:16px}}
  .card{{background:#1e293b;padding:32px;border-radius:14px;max-width:380px;width:100%;
        box-shadow:0 10px 40px rgba(0,0,0,.45)}}
  h1{{font-size:19px;margin:0 0 6px}} .sub{{font-size:14px;color:#94a3b8;margin:0 0 20px}}
  label{{display:block;font-size:13px;margin-bottom:6px;color:#cbd5e1}}
  input[type=password]{{width:100%;padding:11px 12px;border-radius:8px;border:1px solid #334155;
        background:#0f172a;color:#e2e8f0;font-size:14px}}
  button{{margin-top:20px;width:100%;padding:11px;border:0;border-radius:8px;background:#6366f1;
        color:#fff;font-size:15px;font-weight:600;cursor:pointer}}
  button:hover{{background:#4f46e5}} .err{{color:#f87171;font-size:13px;margin:0 0 14px}}
</style></head><body>
<form class="card" method="post" action="{action}">
  <h1>Connect Google Calendar</h1>
  <p class="sub">Enter your API key to authorize this connector.</p>
  {err_html}
  <label for="k">API key</label>
  <input id="k" type="password" name="api_key" autocomplete="off" autofocus required>
  {hidden}
  <button type="submit">Authorize</button>
</form></body></html>"""
    return HTMLResponse(
        page,
        status_code=status,
        headers={
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "form-action 'self'; frame-ancestors 'none'"
            ),
            "Referrer-Policy": "no-referrer",
        },
    )


@mcp_oauth_router.get("/authorize")
async def authorize_get(request: Request):
    try:
        _base_url()
    except OAuthConfigError as exc:
        return HTMLResponse(_error_page(str(exc)), status_code=500)

    q = request.query_params
    client_id = q.get("client_id")
    redirect_uri = q.get("redirect_uri")
    response_type = q.get("response_type")
    code_challenge = q.get("code_challenge")
    code_challenge_method = q.get("code_challenge_method", "")
    state = q.get("state")
    scope = q.get("scope", "mcp")

    # We can only safely redirect errors to a validated redirect_uri; otherwise
    # show an error page (never redirect to an untrusted target).
    if not redirect_uri or not is_allowed_redirect_uri(redirect_uri):
        return HTMLResponse(_error_page("Invalid or missing redirect_uri."), status_code=400)
    if not client_id:
        return _redirect_error(redirect_uri, state, "invalid_request", "client_id is required")
    if response_type != "code":
        return _redirect_error(redirect_uri, state, "unsupported_response_type",
                               "only response_type=code is supported")
    if not code_challenge or code_challenge_method != "S256":
        return _redirect_error(redirect_uri, state, "invalid_request",
                               "PKCE with code_challenge_method=S256 is required")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "state": state or "",
        "scope": scope,
    }
    return _consent_page(params)


@mcp_oauth_router.post("/authorize")
async def authorize_post(
    api_key: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: str = Form("code"),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form("S256"),
    state: str = Form(""),
    scope: str = Form("mcp"),
):
    try:
        _base_url()
    except OAuthConfigError as exc:
        return HTMLResponse(_error_page(str(exc)), status_code=500)

    if not is_allowed_redirect_uri(redirect_uri):
        return HTMLResponse(_error_page("Invalid redirect_uri."), status_code=400)
    if not code_challenge or code_challenge_method != "S256":
        return _redirect_error(redirect_uri, state or None, "invalid_request",
                               "PKCE with code_challenge_method=S256 is required")

    if not settings.api_key or not hmac.compare_digest(api_key, settings.api_key):
        logger.warning("mcp-oauth: authorize denied (invalid API key) client=%s", client_id)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": response_type,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "scope": scope,
        }
        return _consent_page(params, error="Invalid API key. Please try again.")

    code = issue_auth_code(client_id, redirect_uri, code_challenge, scope)
    logger.info("mcp-oauth: issued authorization code for client=%s", client_id)
    params = {"code": code}
    if state:
        params["state"] = state
    return _redirect_with_params(redirect_uri, params)


@mcp_oauth_router.post("/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    code_verifier: str = Form(None),
    refresh_token: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    scope: str = Form(""),
):
    try:
        _base_url()
        _signing_key()
    except OAuthConfigError as exc:
        return _server_error(exc)

    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            return _token_error("invalid_request", "code, redirect_uri and code_verifier are required")
        claims = consume_auth_code(code, redirect_uri, code_verifier, client_id)
        if not claims:
            return _token_error("invalid_grant", "invalid or expired authorization code")
        return _token_response(claims.get("sub", client_id or "mcp-client"),
                               claims.get("scope", ""), with_refresh=True)

    if grant_type == "refresh_token":
        if not refresh_token:
            return _token_error("invalid_request", "refresh_token is required")
        claims = _decode_refresh_token(refresh_token)
        if not claims:
            return _token_error("invalid_grant", "invalid or expired refresh token")
        return _token_response(claims.get("sub", "mcp-client"), claims.get("scope", ""), with_refresh=True)

    if grant_type == "client_credentials":
        if not (settings.oauth_client_id and settings.oauth_client_secret):
            return _token_error("unauthorized_client", "client_credentials grant is not enabled")
        if client_id != settings.oauth_client_id or client_secret != settings.oauth_client_secret:
            return _token_error("invalid_client", "invalid client credentials", status=401)
        return _token_response(client_id, scope, with_refresh=False)

    return _token_error("unsupported_grant_type", f"unsupported grant_type: {grant_type}")


def _token_response(subject: str, scope: str, with_refresh: bool) -> JSONResponse:
    body = {
        "access_token": issue_access_token(subject, scope),
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL,
    }
    if scope:
        body["scope"] = scope
    if with_refresh:
        body["refresh_token"] = issue_refresh_token(subject, scope)
    return JSONResponse(body, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


def _token_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": error, "error_description": description},
        status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
