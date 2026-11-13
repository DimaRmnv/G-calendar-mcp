"""Credentials that ride in a request URL never reach the server's log.

The API key is accepted as `?api_key=` and as a `/key/{key}/` path segment, the
Google start link carries a signed `?token=`, and the Google callback carries
the authorization `code` and `state`. uvicorn writes the path and the whole
query string of every request to its log, so each of these would be written down
in plain text. The end-to-end test runs the real application under a real uvicorn
server with the logging configuration `serve()` hands to uvicorn, sends exact
request targets over a socket, and reads what the log handlers print. For every
spelling of the key the auth middleware accepts, it checks that the server did
accept it and that the log does not hold it.
"""
from __future__ import annotations

import io
import logging
import socket
import threading
import time

import pytest
import uvicorn

import google_calendar.server as server_module
from google_calendar.settings import settings

KEY = "REALKEY-9f8e7d6c"
WRONG = "WRONGKEY-1a2b3c4d"
OTHER_SECRETS = ("ST-4d6f6e33", "CC-5e5a7f44", "CS-6f4b8a55", 'AB"CD')
ACCOUNTS = "/oauth/accounts"  # an authenticated route


def _shipped_uvicorn_kwargs() -> dict:
    """The keyword arguments `serve()` passes to uvicorn.run in HTTP mode."""
    captured: dict = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "transport_mode", "http")
        mp.setattr(server_module, "create_http_app", lambda: object())
        mp.setattr(uvicorn, "run", lambda app, **kw: captured.update(kw))
        server_module.serve()
    assert captured, "serve() did not start uvicorn"
    return captured


@pytest.fixture
def served(monkeypatch, tmp_path):
    """The real app on a free loopback port, logging as production does.

    Yields `send(target, websocket=False) -> status` and the text the log handlers wrote.
    """
    monkeypatch.setenv("HOME", str(tmp_path))  # no accounts, no tokens
    monkeypatch.setattr(settings, "api_key", KEY, raising=False)
    monkeypatch.setattr(settings, "server_base_url", "https://stand.example/calendar/mcp",
                        raising=False)
    kwargs = _shipped_uvicorn_kwargs()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(server_module.create_http_app(), log_level=kwargs["log_level"],
                            log_config=kwargs["log_config"])
    # uvicorn configured its loggers in Config(); point their handlers at a buffer so the
    # formatted lines, after every handler filter, can be read back.
    buffer = io.StringIO()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "google_calendar"):
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

    def send(target: str, websocket: bool = False) -> int:
        headers = ("Upgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
                   if websocket else "Connection: close\r\n")
        with socket.create_connection(("127.0.0.1", port), timeout=10) as conn:
            conn.sendall(f"GET {target} HTTP/1.1\r\nHost: 127.0.0.1\r\n{headers}\r\n".encode())
            status_line = conn.recv(4096).split(b"\r\n", 1)[0]
        return int(status_line.split()[1])

    yield send, buffer
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


# Spellings of the key the auth middleware accepts: the answer is anything but 401.
ACCEPTED = [
    f"/mcp/calendar{ACCOUNTS}?api_key={KEY}&keep=visible",
    f"/mcp/calendar{ACCOUNTS}?api%5Fkey={KEY}",
    f"/mcp/calendar/key/{KEY}{ACCOUNTS}",
    f"/mcp/calendar/k%09ey/{KEY}{ACCOUNTS}",
    f"/mcp/calendar/%0Akey/{KEY}{ACCOUNTS}",
    f"/mcp/calendar/key%0D/{KEY}{ACCOUNTS}",
    f"/mcp/calendar/ke%09y/{KEY}{ACCOUNTS}",
]
# Whether the server reads this as the key depends on the Starlette version (1.3 does,
# 1.10 does not); either way it is never written down.
EITHER_WAY = [
    f"/mcp/calendar/key/{KEY}%3Fx{ACCOUNTS}",
]
# WebSocket lines are written on uvicorn.error with the whole path and query as one
# argument; a quote in the query must not end the redaction early.
WEBSOCKET_QUOTED = [
    f"/mcp/calendar/mcp?x='&api_key={KEY}",
    f'/mcp/calendar/mcp?x="&api_key={KEY}',
    '/mcp/calendar/mcp?note="hi"&code=CC-5e5a7f44&state=CS-6f4b8a55',
    f"/mcp/calendar/mcp?api_key='s-{KEY}",
]
# The real key in forms the server refuses (401): still never written down.
REFUSED = [
    f"/mcp/calendar{ACCOUNTS}?x=1;api_key={KEY}",
    f"/mcp/calendar{ACCOUNTS}??api_key={KEY}",
]


def test_url_credentials_never_reach_the_log(served):
    send, buffer = served

    assert send(f"/mcp/calendar/key/{WRONG}{ACCOUNTS}") == 401  # the path key is checked
    for target in ACCEPTED:
        assert send(target) != 401, f"auth refused {target}"
    for target in REFUSED:
        assert send(target) == 401, f"auth accepted {target}"
    for target in EITHER_WAY:
        send(target)
    send("/mcp/calendar/oauth/start/work?token=ST-4d6f6e33")
    send("/mcp/calendar/oauth/callback?code=CC-5e5a7f44&state=CS-6f4b8a55")
    send('/mcp/calendar/oauth/callback?code=AB"CD&state=x')
    send(f"/mcp/calendar/mcp?api_key={KEY}", websocket=True)
    for target in WEBSOCKET_QUOTED:
        send(target, websocket=True)
    time.sleep(0.3)
    log = buffer.getvalue()

    # Every request was logged, so the absence below is not vacuous.
    assert log.count('"GET /mcp/calendar/') == 1 + len(ACCEPTED) + len(REFUSED) + len(EITHER_WAY) + 3, log
    assert '"WebSocket /mcp/calendar/mcp?api_key=REDACTED"' in log, log
    assert log.count('"WebSocket /mcp/calendar/mcp?') == 1 + len(WEBSOCKET_QUOTED), log
    assert KEY not in log, log
    for secret in OTHER_SECRETS:
        assert secret not in log, log
    assert WRONG not in log, log  # a wrong key may be a mistyped real one
    assert "keep=visible" in log
    assert "/mcp/calendar/key/REDACTED/oauth/accounts" in log
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
    ('/p?code=AB"CD&state=x', "/p?code=REDACTED&state=REDACTED"),
    ("/p?x=1;api_key=k", "/p?x=1;api_key=REDACTED"),
    ("/p??api_key=k", "/p??api_key=REDACTED"),
    ("/p?api_key", "/p?api_key"),
    ("/mcp/calendar/key/abc/mcp", "/mcp/calendar/key/REDACTED/mcp"),
    ("/mcp/calendar/key/abc", "/mcp/calendar/key/REDACTED"),
    ("/mcp/calendar/key/abc?x=1", "/mcp/calendar/key/REDACTED?x=1"),
    ("/mcp/calendar/k%09ey/abc/mcp", "/mcp/calendar/key/REDACTED/mcp"),
    ("/a/key/k1/b/key/k2/c", "/a/key/REDACTED/b/key/REDACTED/c"),
    ("/mcp/calendar/export/0b9f1c1e?x=1", "/mcp/calendar/export/0b9f1c1e?x=1"),
    ("/mcp/calendar/te%20st?x=1", "/mcp/calendar/te%20st?x=1"),
    ("/a%1Bb/key/k/c%1Bd%0A", "/a%1Bb/key/REDACTED/c%1Bd"),
])
def test_redact_url(text, expected):
    from google_calendar.log_redaction import redact_url

    assert redact_url(text) == expected


@pytest.mark.parametrize("hostile", [
    "/p?" + "?" * 64_000,
    "/p" + "?x" * 32_000,
    "/p?" + "&" * 64_000,
    "/p?" + "a" * 64_000 + "=",
    "/key/" * 13_000,
    "/p?" + "api_key=" * 8_000,
], ids=["question-marks", "question-x", "ampersands", "long-name", "key-segments", "names"])
def test_a_long_hostile_url_is_redacted_in_linear_time(hostile):
    # The filter runs on the event loop for every request; one slow URL stalls the server.
    from google_calendar.log_redaction import redact_text, redact_url

    started = time.perf_counter()
    redact_url(hostile)
    redact_text(f'127.0.0.1 - "GET {hostile} HTTP/1.1" 200')
    assert time.perf_counter() - started < 0.5


def _record(name, msg, args, **extra):
    record = logging.LogRecord(name, logging.INFO, __file__, 1, msg, args, None)
    record.__dict__.update(extra)
    return record


def test_the_access_record_keeps_its_five_arguments():
    from google_calendar.log_redaction import RedactSecretsFilter

    record = _record("uvicorn.access", '%s - "%s %s HTTP/%s" %d',
                     ("1.2.3.4:5", "GET", "/p?api_key=k", "1.1", 200))
    assert RedactSecretsFilter().filter(record) is True
    assert record.args == ("1.2.3.4:5", "GET", "/p?api_key=REDACTED", "1.1", 200)


@pytest.mark.parametrize("msg, args, expected", [
    ("callback /cb?code=%s received", ("GOOGLE-CODE-123",), "callback /cb?code=REDACTED received"),
    ("bytes %s", (b"/p?api_key=k",), "bytes b'/p?api_key=REDACTED'"),
    ("%(u)s", ({"u": "/p?token=t"},), "/p?token=REDACTED"),
    ("%(u)s", ({"u": "/p?q='&token=t"},), "/p?q='&token=REDACTED"),
    ('%s - "WebSocket %s" 403', ("1.2.3.4:5", "/x/key/k/y"),
     '1.2.3.4:5 - "WebSocket /x/key/REDACTED/y" 403'),
    ('%s - "WebSocket %s" 403', ("1.2.3.4:5", "/x?q='&api_key=k"),
     '1.2.3.4:5 - "WebSocket /x?q=\'&api_key=REDACTED" 403'),
    ("seen /x/key/k/y in a template", (), "seen /x/key/REDACTED/y in a template"),
    ("%s %s", ("only-one",), "%s %s [log arguments dropped: they did not fit the message]"),
    ("%(u)s %(missing)s", ({"u": "x"},),
     "%(u)s %(missing)s [log arguments dropped: they did not fit the message]"),
    ("50%% done %(u", ({"u": "x"},), "50%% done %(u [log arguments dropped: they did not fit the message]"),
], ids=["template", "bytes", "dict", "dict-quote", "websocket", "websocket-quote", "path-in-template",
        "broken-type", "broken-key", "broken-value"])
def test_any_other_record_is_formatted_then_redacted(msg, args, expected):
    from google_calendar.log_redaction import RedactSecretsFilter

    record = _record("uvicorn.error", msg, args, color_message=msg)
    assert RedactSecretsFilter().filter(record) is True
    assert record.getMessage() == expected
    assert "color_message" not in record.__dict__


def test_a_record_without_credentials_is_left_as_it_was():
    from google_calendar.log_redaction import RedactSecretsFilter

    color = "Started server process [\x1b[36m%d\x1b[0m]"
    record = _record("uvicorn.error", "Started server process [%d] on http://0.0.0.0:8000",
                     (42,), color_message=color)
    RedactSecretsFilter().filter(record)
    assert (record.msg, record.args) == ("Started server process [%d] on http://0.0.0.0:8000", (42,))
    assert record.__dict__["color_message"] == color


def test_uvicorns_own_default_config_is_left_untouched():
    import copy

    from uvicorn.config import LOGGING_CONFIG

    from google_calendar.log_redaction import uvicorn_log_config

    before = copy.deepcopy(LOGGING_CONFIG)
    uvicorn_log_config()
    assert LOGGING_CONFIG == before
