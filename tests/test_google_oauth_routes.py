"""The Google-OAuth routes of the HTTP server (/mcp/calendar/oauth/*).

These routes store the Google token every calendar call runs on, so:
- only a link minted by the server itself may start a flow for an account;
- the callback saves a token only for the Google identity configured for that
  account;
- account names and e-mails are not served to anonymous callers;
- request data echoed into a page is escaped and the pages carry a CSP.
"""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

import google_calendar.oauth_server as oauth_server
from google_calendar import oauth_links
from google_calendar.settings import settings

API_KEY = "test-api-key-oauth-routes"
BASE_URL = "https://stand.example/calendar/mcp"
OWNER = "owner@example.test"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    app_dir = tmp_path / ".mcp" / "google-calendar"
    app_dir.mkdir(parents=True)
    (app_dir / "config.json").write_text(json.dumps({
        "default_account": "work",
        "accounts": {"work": {"email": OWNER}, "personal": {"email": "other@example.test"}},
    }))
    (app_dir / "oauth_client.json").write_text(json.dumps({"web": {
        "client_id": "cid.apps.googleusercontent.com", "client_secret": "secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}))
    monkeypatch.setattr(settings, "api_key", API_KEY, raising=False)
    monkeypatch.setattr(settings, "server_base_url", BASE_URL, raising=False)
    monkeypatch.setattr(settings, "oauth_redirect_uri", f"{BASE_URL}/oauth/callback", raising=False)

    from google_calendar.server import create_http_app
    return TestClient(create_http_app(), follow_redirects=False)


def _local(url: str) -> str:
    """The app-relative path + query of a public URL minted by the server."""
    parsed = urlparse(url)
    return "/mcp/calendar" + parsed.path.removeprefix("/calendar/mcp") + (f"?{parsed.query}" if parsed.query else "")


def _start(client, account="work"):
    r = client.get(_local(settings.get_auth_start_url(account)))
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)["state"][0]


# ---------------------------------------------------------------------------
# Starting a flow
# ---------------------------------------------------------------------------

def test_a_link_minted_by_the_server_starts_the_flow(client):
    url = settings.get_auth_start_url("work")

    r = client.get(_local(url))

    assert r.status_code == 302
    assert r.headers["location"].startswith("https://accounts.google.com/")


def _forged(account):
    return oauth_links.mint(account).rsplit(".", 1)[0] + ".AAAA"


@pytest.mark.parametrize("query", [
    "",                                                     # no token
    "?token=garbage",
    "?token=" + "x" * 40 + "." + "y" * 40,
])
def test_start_without_a_valid_link_is_refused(client, query):
    r = client.get(f"/mcp/calendar/oauth/start/work{query}")

    assert r.status_code == 403
    assert "location" not in r.headers


def test_start_with_a_forged_signature_is_refused(client):
    r = client.get(f"/mcp/calendar/oauth/start/work?token={_forged('work')}")

    assert r.status_code == 403


def test_start_with_a_link_for_another_account_is_refused(client):
    token = oauth_links.mint("personal")

    r = client.get(f"/mcp/calendar/oauth/start/work?token={token}")

    assert r.status_code == 403


def test_start_with_an_expired_link_is_refused(client):
    token = oauth_links.mint("work", now=time.time() - oauth_links.LINK_TTL_SECONDS - 5)

    r = client.get(f"/mcp/calendar/oauth/start/work?token={token}")

    assert r.status_code == 403


def test_a_link_signed_with_another_api_key_is_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "a-rotated-key")
    stale = oauth_links.mint("work")
    monkeypatch.setattr(settings, "api_key", API_KEY)

    r = client.get(f"/mcp/calendar/oauth/start/work?token={stale}")

    assert r.status_code == 403


def test_a_refused_start_does_not_reveal_whether_the_account_exists(client):
    assert client.get("/mcp/calendar/oauth/start/no-such-account").status_code == 403


def test_auth_urls_handed_out_by_the_server_are_signed_links(client):
    url = settings.get_auth_start_url("work")

    token = parse_qs(urlparse(url).query)["token"][0]
    assert url.startswith(f"{BASE_URL}/oauth/start/work?token=")
    assert oauth_links.verify(token, "work")


# ---------------------------------------------------------------------------
# The callback
# ---------------------------------------------------------------------------

@pytest.fixture
def consent(monkeypatch):
    """Stub the code exchange; `consent.email` is who consented, `consent.saved` what was stored."""
    class Consent:
        email = OWNER
        saved: list = []

    Consent.saved = []
    creds = object()
    monkeypatch.setattr(oauth_server, "_exchange_code", lambda flow, code: creds)
    monkeypatch.setattr(oauth_server, "_consenting_email", lambda c, account: Consent.email)
    monkeypatch.setattr(oauth_server, "save_credentials", lambda account, c: Consent.saved.append(account))
    return Consent


def test_callback_stores_the_token_of_the_configured_identity(client, consent):
    consent.email = "Owner@Example.TEST"  # Google may change the case
    state = _start(client)

    r = client.get(f"/mcp/calendar/oauth/callback?state={state}&code=c")

    assert r.status_code == 200
    assert consent.saved == ["work"]


def test_callback_refuses_another_google_identity(client, consent):
    consent.email = "stranger@example.test"
    state = _start(client)

    r = client.get(f"/mcp/calendar/oauth/callback?state={state}&code=c")

    assert r.status_code == 403
    assert consent.saved == []
    assert "stranger@example.test" not in r.text


def test_a_state_is_good_for_one_callback_only(client, consent):
    state = _start(client)
    client.get(f"/mcp/calendar/oauth/callback?state={state}&code=c")

    r = client.get(f"/mcp/calendar/oauth/callback?state={state}&code=c")

    assert r.status_code == 400
    assert consent.saved == ["work"]


def test_callback_echoes_nothing_unescaped_and_sends_a_csp(client):
    r = client.get("/mcp/calendar/oauth/callback?error=<script>alert(1)</script>")

    assert r.status_code == 400
    assert "<script>" not in r.text
    assert "&lt;script&gt;" in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"]


# ---------------------------------------------------------------------------
# Account information
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/mcp/calendar/oauth/accounts", "/mcp/calendar/oauth/status/work"])
def test_account_information_needs_authentication(client, path):
    anonymous = client.get(path)
    authed = client.get(path, headers={"X-API-Key": API_KEY})

    assert anonymous.status_code == 401
    assert OWNER not in anonymous.text
    assert authed.status_code == 200


def test_the_mcp_connector_oauth_endpoints_stay_public(client):
    # Claude's connector calls these before it has any credential.
    assert client.post("/mcp/calendar/oauth/token", data={}).status_code != 401
    assert client.get("/mcp/calendar/oauth/authorize").status_code != 401
