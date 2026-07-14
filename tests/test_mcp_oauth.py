"""Tests for the OAuth 2.1 authorization server used by MCP clients (Claude).

Covers the flow Claude's custom-connector performs on connect: discovery
metadata, dynamic client registration, authorization-code + PKCE, token issuance
and refresh, and the protected-resource 401 challenge. See mcp_oauth.py.
"""
from __future__ import annotations

import base64
import hashlib
import os
from urllib.parse import parse_qs, urlparse

import pytest

from google_calendar import mcp_oauth
from google_calendar.settings import settings

BASE_URL = "https://viredge.com/calendar/mcp"
API_KEY = "test-api-key-abc123"
REDIRECT = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture(autouse=True)
def _configure(monkeypatch):
    """Point the AS at a known base URL / API key and reset the replay cache."""
    monkeypatch.setattr(settings, "server_base_url", BASE_URL, raising=False)
    monkeypatch.setattr(settings, "api_key", API_KEY, raising=False)
    mcp_oauth._consumed_codes.clear()
    yield
    mcp_oauth._consumed_codes.clear()


def _pkce_pair():
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def test_pkce_roundtrip():
    verifier, challenge = _pkce_pair()
    assert mcp_oauth.verify_pkce(verifier, challenge)


def test_pkce_rejects_wrong_verifier():
    _, challenge = _pkce_pair()
    assert not mcp_oauth.verify_pkce("wrong-verifier", challenge)
    assert not mcp_oauth.verify_pkce("", challenge)


def test_access_token_roundtrip():
    token = mcp_oauth.issue_access_token("client-1", "mcp")
    assert mcp_oauth.verify_bearer_token(token)


def test_verify_rejects_refresh_and_garbage():
    assert not mcp_oauth.verify_bearer_token(mcp_oauth.issue_refresh_token("c"))  # wrong typ
    assert not mcp_oauth.verify_bearer_token("not.a.jwt")
    assert not mcp_oauth.verify_bearer_token("")


def test_access_token_invalidated_when_api_key_rotates(monkeypatch):
    token = mcp_oauth.issue_access_token("client-1")
    monkeypatch.setattr(settings, "api_key", "rotated-key", raising=False)
    assert not mcp_oauth.verify_bearer_token(token)  # signing key derives from api_key


def test_auth_code_roundtrip():
    verifier, challenge = _pkce_pair()
    code = mcp_oauth.issue_auth_code("client-1", REDIRECT, challenge, "mcp")
    claims = mcp_oauth.consume_auth_code(code, REDIRECT, verifier)
    assert claims is not None
    assert claims["sub"] == "client-1"


def test_auth_code_rejects_bad_verifier():
    _, challenge = _pkce_pair()
    code = mcp_oauth.issue_auth_code("c", REDIRECT, challenge)
    assert mcp_oauth.consume_auth_code(code, REDIRECT, "nope") is None


def test_auth_code_rejects_redirect_mismatch():
    verifier, challenge = _pkce_pair()
    code = mcp_oauth.issue_auth_code("c", REDIRECT, challenge)
    assert mcp_oauth.consume_auth_code(code, "https://claude.ai/other", verifier) is None


def test_auth_code_is_single_use():
    verifier, challenge = _pkce_pair()
    code = mcp_oauth.issue_auth_code("c", REDIRECT, challenge)
    assert mcp_oauth.consume_auth_code(code, REDIRECT, verifier) is not None
    assert mcp_oauth.consume_auth_code(code, REDIRECT, verifier) is None  # replay rejected


def test_auth_code_bound_to_client():
    verifier, challenge = _pkce_pair()
    code = mcp_oauth.issue_auth_code("client-A", REDIRECT, challenge)
    # A different client_id on redemption is rejected (and must not consume the code)...
    assert mcp_oauth.consume_auth_code(code, REDIRECT, verifier, client_id="client-B") is None
    # ...the correct client_id still succeeds.
    assert mcp_oauth.consume_auth_code(code, REDIRECT, verifier, client_id="client-A") is not None


def test_refresh_token_decode():
    claims = mcp_oauth._decode_refresh_token(mcp_oauth.issue_refresh_token("client-1", "mcp"))
    assert claims and claims["sub"] == "client-1"
    # an access token must not pass as a refresh token
    assert mcp_oauth._decode_refresh_token(mcp_oauth.issue_access_token("client-1")) is None


@pytest.mark.parametrize(
    "uri,ok",
    [
        ("https://claude.ai/api/mcp/auth_callback", True),
        ("https://foo.claude.ai/cb", True),
        ("https://claude.com/cb", True),
        ("http://localhost:8976/cb", True),
        ("http://127.0.0.1:1/cb", True),
        ("https://evil.com/cb", False),
        ("https://claude.ai.evil.com/cb", False),
        ("http://claude.ai/cb", False),  # plain http only allowed for loopback
        ("ftp://claude.ai/cb", False),
        ("", False),
        ("https://anthropic.com/cb", True),
        ("https://evil.com\\@claude.ai/cb", False),  # backslash parser confusion
        ("https://evil.com\\.claude.ai/cb", False),  # backslash parser confusion
        ("https://evil.localhost/cb", False),  # loopback is exact-match only, never subdomain
        ("http://[::1]:9/cb", True),  # ipv6 loopback
    ],
)
def test_redirect_allowlist(uri, ok):
    assert mcp_oauth.is_allowed_redirect_uri(uri) is ok


def test_protected_resource_metadata():
    md = mcp_oauth.protected_resource_metadata()
    assert md["resource"] == f"{BASE_URL}/mcp"
    assert md["authorization_servers"] == [BASE_URL]


def test_authorization_server_metadata():
    md = mcp_oauth.authorization_server_metadata()
    assert md["issuer"] == BASE_URL
    assert md["authorization_endpoint"] == f"{BASE_URL}/oauth/authorize"
    assert md["token_endpoint"] == f"{BASE_URL}/oauth/token"
    assert md["registration_endpoint"] == f"{BASE_URL}/oauth/register"
    assert md["code_challenge_methods_supported"] == ["S256"]
    assert "authorization_code" in md["grant_types_supported"]


def test_www_authenticate_points_at_metadata():
    val = mcp_oauth.www_authenticate_value()
    assert val.startswith("Bearer ")
    assert f'resource_metadata="{BASE_URL}/.well-known/oauth-protected-resource"' in val


# --------------------------------------------------------------------------
# HTTP endpoints (via the real FastAPI app, no DB / no lifespan)
# --------------------------------------------------------------------------

@pytest.fixture
def client():
    from starlette.testclient import TestClient

    from google_calendar.server import create_http_app

    # No `with` -> lifespan (MCP session manager / cleanup task) is not started;
    # every route we exercise here is resolved before the MCP mount.
    return TestClient(create_http_app())


def test_prm_endpoint(client):
    r = client.get("/mcp/calendar/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    assert r.json()["resource"] == f"{BASE_URL}/mcp"


def test_asm_endpoint(client):
    r = client.get("/mcp/calendar/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["registration_endpoint"].endswith("/oauth/register")


def test_dynamic_client_registration(client):
    r = client.post(
        "/mcp/calendar/oauth/register",
        json={"redirect_uris": [REDIRECT], "client_name": "Claude"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["client_id"]
    assert body["token_endpoint_auth_method"] == "none"


def test_registration_rejects_bad_redirect(client):
    r = client.post(
        "/mcp/calendar/oauth/register",
        json={"redirect_uris": ["https://evil.com/cb"]},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"


def test_authorize_get_renders_consent(client):
    _, challenge = _pkce_pair()
    r = client.get(
        "/mcp/calendar/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "c1",
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
        },
    )
    assert r.status_code == 200
    assert "API key" in r.text
    assert challenge in r.text  # carried through as a hidden field


def test_authorize_get_rejects_bad_redirect(client):
    _, challenge = _pkce_pair()
    r = client.get(
        "/mcp/calendar/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "c1",
            "redirect_uri": "https://evil.com/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert r.status_code == 400


def test_authorize_post_wrong_key(client):
    _, challenge = _pkce_pair()
    r = client.post(
        "/mcp/calendar/oauth/authorize",
        data={
            "api_key": "WRONG",
            "client_id": "c1",
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": "mcp",
        },
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "Invalid API key" in r.text


def test_full_authorization_code_flow(client):
    verifier, challenge = _pkce_pair()

    reg = client.post(
        "/mcp/calendar/oauth/register",
        json={"redirect_uris": [REDIRECT], "client_name": "Claude"},
    )
    client_id = reg.json()["client_id"]

    auth = client.post(
        "/mcp/calendar/oauth/authorize",
        data={
            "api_key": API_KEY,
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": "mcp",
        },
        follow_redirects=False,
    )
    assert auth.status_code == 302
    q = parse_qs(urlparse(auth.headers["location"]).query)
    assert q["state"] == ["xyz"]
    code = q["code"][0]

    tok = client.post(
        "/mcp/calendar/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )
    assert tok.status_code == 200
    body = tok.json()
    assert body["token_type"] == "Bearer"
    assert mcp_oauth.verify_bearer_token(body["access_token"])
    assert body["refresh_token"]

    ref = client.post(
        "/mcp/calendar/oauth/token",
        data={"grant_type": "refresh_token", "refresh_token": body["refresh_token"]},
    )
    assert ref.status_code == 200
    assert mcp_oauth.verify_bearer_token(ref.json()["access_token"])


def test_token_rejects_bad_pkce(client):
    _, challenge = _pkce_pair()
    auth = client.post(
        "/mcp/calendar/oauth/authorize",
        data={
            "api_key": API_KEY,
            "client_id": "c1",
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(auth.headers["location"]).query)["code"][0]
    tok = client.post(
        "/mcp/calendar/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "code_verifier": "wrong-verifier",
        },
    )
    assert tok.status_code == 400
    assert tok.json()["error"] == "invalid_grant"


def test_mcp_endpoint_challenges_unauthenticated(client):
    r = client.post(
        "/mcp/calendar/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert r.status_code == 401
    assert "resource_metadata" in r.headers.get("WWW-Authenticate", "")


def test_mcp_endpoint_accepts_oauth_bearer():
    """End-to-end: a token minted by our AS is accepted by the MCP endpoint."""
    from starlette.testclient import TestClient

    from google_calendar.server import create_http_app

    token = mcp_oauth.issue_access_token("client-1", "mcp")
    with TestClient(create_http_app()) as c:
        r = c.post(
            "/mcp/calendar/mcp",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"},
                },
            },
        )
    assert r.status_code == 200
