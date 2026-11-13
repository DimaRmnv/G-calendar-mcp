"""The application's own log lines reach the server log, with credentials redacted.

Nothing configured the `google_calendar` loggers, so only WARNING and above reached
the container log through Python's last-resort handler: the export cleanup's INFO
line, which CLAUDE.md tells operators to grep for, never appeared, and an input
error left only fastmcp's "Error calling tool '<name>'" without its reason. The
logging configuration `serve()` hands to uvicorn now also covers the app's logger,
through the same redaction filter as uvicorn's handlers.
"""
from __future__ import annotations

import io
import logging
import logging.config

import pytest
import uvicorn
from fastmcp import Client

import google_calendar.server as server_module
from google_calendar.errors import InputError
from google_calendar.settings import settings


@pytest.fixture
def app_log(tmp_path, monkeypatch):
    """Apply the logging configuration serve() ships; yield what the app's handler writes."""
    monkeypatch.setenv("HOME", str(tmp_path))  # no accounts: nothing can reach Google
    logger = logging.getLogger("google_calendar")
    saved = (logger.handlers[:], logger.level, logger.propagate)
    captured: dict = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "transport_mode", "http")
        mp.setattr(server_module, "create_http_app", lambda: object())
        mp.setattr(uvicorn, "run", lambda app, **kw: captured.update(kw))
        server_module.serve()
    logging.config.dictConfig(captured["log_config"])
    buffer = io.StringIO()
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(buffer)
    yield buffer
    logger.handlers[:], logger.propagate = saved[0], saved[2]
    logger.setLevel(saved[1])


def test_an_info_line_of_the_app_is_written_with_its_level_and_logger(app_log):
    logging.getLogger("google_calendar.export_router").info(
        "Cleanup: deleted %d expired report files", 2)
    logging.getLogger("google_calendar.export_router").debug("not at INFO")

    lines = app_log.getvalue().splitlines()
    assert len(lines) == 1, lines
    assert "INFO" in lines[0]
    assert "google_calendar.export_router" in lines[0]
    assert lines[0].endswith("Cleanup: deleted 2 expired report files")


def test_a_credential_in_an_app_line_is_redacted(app_log):
    logging.getLogger("google_calendar.api.client").warning(
        "Authorize here: %s", "https://stand.example/calendar/mcp/oauth/start/work?token=abc123")

    text = app_log.getvalue()
    assert "abc123" not in text
    assert "oauth/start/work?token=REDACTED" in text


async def test_an_input_error_writes_its_reason(app_log):
    async with Client(server_module.mcp) as client:
        result = await client.call_tool("events", {"action": "list", "time_min": "2026-13-45"},
                                        raise_on_error=False)

    assert result.is_error
    assert "Invalid time bound '2026-13-45'" in app_log.getvalue()


def test_a_line_break_in_a_reason_cannot_forge_a_log_line(app_log):
    InputError("bad value\nINFO: forged line")

    lines = app_log.getvalue().splitlines()
    assert len(lines) == 1, lines
    assert "forged line" in lines[0]
