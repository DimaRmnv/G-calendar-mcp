"""Credentials that ride in a request URL never reach the server's log.

The API key is accepted as `?api_key=` and as a `/key/{key}/` path segment, the
Google start link carries a signed `?token=`, and the Google callback carries
the authorization `code` and `state`. uvicorn writes the path and the whole
query string of every request to its access log, so each of these would be
written down in plain text. These tests run a real uvicorn server with the
logging configuration `serve()` hands to uvicorn and read what it prints.
"""
from __future__ import annotations

import io
import logging
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

import google_calendar.server as server_module
from google_calendar.settings import settings

SECRETS = {
    "query_key": "QK-1f0a9e7c",
    "encoded_name_key": "EK-2b8d4c11",
    "path_key": "PK-3c7e5d22",
    "start_token": "ST-4d6f6e33",
    "callback_code": "CC-5e5a7f44",
    "callback_state": "CS-6f4b8a55",
    "websocket_key": "WK-7a3c9b66",
}


def _shipped_uvicorn_kwargs(monkeypatch) -> dict:
    """The keyword arguments `serve()` passes to uvicorn.run in HTTP mode."""
    captured: dict = {}
    monkeypatch.setattr(settings, "transport_mode", "http")
    monkeypatch.setattr(server_module, "create_http_app", lambda: object())
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(kw))
    server_module.serve()
    assert captured, "serve() did not start uvicorn"
    return captured


def _app() -> Starlette:
    async def ok(request):
        return PlainTextResponse("ok")
    return Starlette(routes=[Route("/{path:path}", ok)])


@pytest.fixture
def served(monkeypatch):
    """A real uvicorn server on a free loopback port, logging as production does.

    Yields a GET function and the text every uvicorn log handler wrote.
    """
    kwargs = _shipped_uvicorn_kwargs(monkeypatch)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(_app(), log_level=kwargs.get("log_level", "info"),
                            log_config=kwargs.get("log_config", uvicorn.config.LOGGING_CONFIG))
    # uvicorn configured its loggers in Config(); point their handlers at a buffer
    # so the formatted lines, after every handler filter, can be read back.
    buffer = io.StringIO()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setStream(buffer)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.02)

    def get(path: str) -> None:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).read()
        except urllib.error.HTTPError:
            pass

    def websocket(path: str) -> None:
        """An upgrade request; uvicorn logs these on uvicorn.error, not the access log."""
        with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
            conn.sendall((f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\n"
                          "Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                          "Sec-WebSocket-Version: 13\r\n\r\n").encode())
            conn.recv(4096)

    get.websocket = websocket
    yield get, buffer
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def test_url_credentials_never_reach_the_access_log(served):
    get, buffer = served
    s = SECRETS
    get(f"/mcp/calendar/mcp?api_key={s['query_key']}&keep=visible")
    get(f"/mcp/calendar/mcp?api%5Fkey={s['encoded_name_key']}")
    get(f"/mcp/calendar/key/{s['path_key']}/mcp")
    get(f"/mcp/calendar/oauth/start/work?token={s['start_token']}")
    get(f"/mcp/calendar/oauth/callback?code={s['callback_code']}&state={s['callback_state']}")
    get.websocket(f"/mcp/calendar/mcp?api_key={s['websocket_key']}")
    time.sleep(0.2)
    log = buffer.getvalue()

    # The requests were logged at all, so the absence below is not vacuous.
    assert log.count('"GET /mcp/calendar/') == 5, log
    assert '"WebSocket /mcp/calendar/mcp?api_key=REDACTED"' in log, log
    for name, secret in SECRETS.items():
        assert secret not in log, f"{name} written to the access log"
    assert "keep=visible" in log
    assert "/mcp/calendar/key/REDACTED/mcp" in log
    assert "api_key=REDACTED" in log
    assert "code=REDACTED&state=REDACTED" in log


@pytest.mark.parametrize("text, expected", [
    ("/p?api_key=abc", "/p?api_key=REDACTED"),
    ("/p?a=1&API_KEY=abc&b=2", "/p?a=1&API_KEY=REDACTED&b=2"),
    ("/p?api%5Fkey=abc", "/p?api%5Fkey=REDACTED"),
    ("/p?api+key=abc", "/p?api+key=abc"),
    ("/p?api_key=a&api_key=b", "/p?api_key=REDACTED&api_key=REDACTED"),
    ("/p?token=t&refresh_token=r&access_token=a&client_secret=c&secret=s",
     "/p?token=REDACTED&refresh_token=REDACTED&access_token=REDACTED"
     "&client_secret=REDACTED&secret=REDACTED"),
    ("/p?code_challenge=x&code=y", "/p?code_challenge=x&code=REDACTED"),
    ("/p?api_key", "/p?api_key"),
    ("/mcp/calendar/key/abc/mcp", "/mcp/calendar/key/REDACTED/mcp"),
    ("/mcp/calendar/key/abc", "/mcp/calendar/key/REDACTED"),
    ("/mcp/calendar/key/abc?x=1", "/mcp/calendar/key/REDACTED?x=1"),
    ('WebSocket /x?api_key=abc" 403', 'WebSocket /x?api_key=REDACTED" 403'),
    ("/mcp/calendar/export/0b9f1c1e?x=1", "/mcp/calendar/export/0b9f1c1e?x=1"),
])
def test_redact(text, expected):
    from google_calendar.log_redaction import redact
    assert redact(text) == expected


def test_filter_redacts_the_message_and_keeps_the_arguments_shape():
    import logging

    from google_calendar.log_redaction import RedactSecretsFilter

    record = logging.LogRecord("x", logging.INFO, __file__, 1,
                               "callback /cb?code=abc %s %s %d", ("/p?token=t", 7, 200), None)
    assert RedactSecretsFilter().filter(record) is True
    assert record.getMessage() == "callback /cb?code=REDACTED /p?token=REDACTED 7 200"
