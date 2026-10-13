"""Which Google OAuth client each account's token is actually bound to.

Needed to identify the client to mark "agentic" in Google Cloud and to spot accounts
whose refresh token still belongs to an old client after the client JSON is swapped.
"""

import json

from google_calendar.cli import auth


def _wire(monkeypatch, tmp_path, token, client):
    token_path = tmp_path / "token.json"
    if token is not None:
        token_path.write_text(token if isinstance(token, str) else json.dumps(token))
    monkeypatch.setattr(auth, "get_token_path", lambda *a: token_path)
    monkeypatch.setattr(auth, "load_oauth_client", lambda *a: client)


def test_reports_token_and_configured_client(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, {"client_id": "old.apps"}, {"web": {"client_id": "new.apps"}})
    assert auth.get_google_client_binding("work") == ("old.apps", "new.apps")


def test_installed_client_format(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, {"client_id": "a.apps"}, {"installed": {"client_id": "a.apps"}})
    assert auth.get_google_client_binding("work") == ("a.apps", "a.apps")


def test_missing_token_and_client(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, None, None)
    assert auth.get_google_client_binding("work") == (None, None)


def test_corrupt_token_file(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, "{not json", {"web": {"client_id": "a.apps"}})
    assert auth.get_google_client_binding("work") == (None, "a.apps")


def test_auth_list_flags_mismatch(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch, tmp_path, {"client_id": "old.apps"}, {"web": {"client_id": "new.apps"}})
    monkeypatch.setattr(auth, "list_accounts", lambda: {"work": {"email": "a@b.c"}})
    monkeypatch.setattr(auth, "is_default", lambda name: True)
    monkeypatch.setattr(auth, "check_token_valid", lambda name: True)
    auth.auth_list()
    out = capsys.readouterr().out
    assert "Google OAuth client: old.apps" in out
    assert "new.apps" in out and "re-authorize" in out
