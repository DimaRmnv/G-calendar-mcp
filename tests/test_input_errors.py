"""A request the caller has to change is answered with its reason and logged as one line.

fastmcp logs any plain exception a tool raises at ERROR with the full traceback and
prefixes the answer with "Error calling tool ...". A wrong parameter (a malformed date,
an unknown timezone, a missing event_id, an unknown account) is the caller's mistake,
not a failure of the server, so it filled the log with tracebacks. Such errors are now
`InputError`: the client reads the reason as written, the log gets one INFO line with
no traceback, and nothing is sent to Google. A real failure keeps ERROR and the
traceback. Every call goes through the MCP client, the path the connector uses.
"""
from __future__ import annotations

import logging

import pytest
from fastmcp import Client

from google_calendar.server import mcp
from tests.test_calendar_api_correctness import install_fake_service

FASTMCP_LOGGER = "fastmcp.server.server"


@pytest.fixture
def fake(monkeypatch, tmp_path):
    return install_fake_service(monkeypatch, tmp_path)


@pytest.fixture(autouse=True)
def _empty_home(tmp_path, monkeypatch):
    # The account config and tokens live under ~/.mcp/google-calendar ($HOME): an empty
    # home means no account, so no test can reach a real Google account.
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def records():
    """Records fastmcp's server logger writes (it does not propagate to the root)."""
    seen: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record):
            seen.append(record)

    logger = logging.getLogger(FASTMCP_LOGGER)
    handler = Keep(level=logging.DEBUG)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield seen
    logger.removeHandler(handler)
    logger.setLevel(old_level)


async def _call(name, arguments):
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments, raise_on_error=False)
    return result.is_error, result.content[0].text


INPUT_ERRORS = [
    ("events", {"action": "list", "time_min": "2026-13-45"},
     "Invalid time bound '2026-13-45': expected a date ('2026-11-09') "
     "or an ISO datetime ('2026-11-09T10:00:00')"),
    ("events", {"action": "list", "time_min": "2026-11-16", "timezone": "Mars/Olympus"},
     "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"),
    ("events", {"action": "list", "time_min": "2026-11-16T10:00:00", "timezone": "Mars/Olympus"},
     "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"),
    ("events", {"action": "list", "period": "today", "timezone": "Mars/Olympus"},
     "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"),
    ("events", {"action": "search", "query": "x", "timezone": "Mars/Olympus"},
     "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"),
    ("events", {"action": "get"}, "event_id is required for 'get' action"),
    ("events", {"action": "update"}, "event_id is required for 'update' action"),
    ("events", {"action": "delete"}, "event_id is required for 'delete' action"),
    ("events", {"action": "create", "start": "2026-11-16T10:00:00", "end": "2026-11-16T11:00:00"},
     "summary is required for 'create' action"),
    ("events", {"action": "search"}, "query is required for 'search' action"),
    ("events", {"action": "batch"}, "operations list is required for 'batch' action"),
    ("events", {"action": "create", "summary": "x"}, "start and end are required for 'create' action"),
    ("calendars", {"action": "get"}, "calendar_id is required for 'get' action"),
    ("calendars", {"action": "update"}, "calendar_id is required for 'update' action"),
    ("calendars", {"action": "delete"}, "calendar_id is required for 'delete' action"),
    ("calendars", {"action": "create"}, "summary is required for 'create' action"),
    ("calendars", {"action": "delete", "calendar_id": "primary"}, "Cannot delete primary calendar"),
    ("calendars", {"action": "set_timezone"}, "timezone parameter required for 'set_timezone' action"),
    ("attendees", {"action": "add", "event_id": "e1"}, "emails parameter required for 'add' action"),
    ("attendees", {"action": "remove", "event_id": "e1"}, "emails parameter required for 'remove' action"),
    ("attendees", {"action": "resend", "event_id": "e1"}, "emails parameter required for 'resend' action"),
    ("attendees", {"action": "respond", "event_id": "e1"}, "response parameter required for 'respond' action"),
    ("attendees", {"action": "respond", "event_id": "e1", "response": "maybe"},
     "Invalid response: maybe. Use one of: accepted, declined, tentative"),
    ("availability", {"action": "query", "time_min": "2026-11-16"},
     "time_min and time_max are required for 'query' action"),
    ("availability", {"action": "find_slots", "time_min": "2026-11-16", "time_max": "2026-11-16"},
     "duration_minutes is required for 'find_slots' action"),
    ("availability", {"action": "find_slots", "duration_minutes": 30},
     "time_min and time_max are required for 'find_slots' action"),
    ("availability", {"action": "find_slots", "time_min": "2026-11-16", "time_max": "2026-11-16",
                      "duration_minutes": 30, "participant_timezones": ["Nowhere/City"]},
     "Unknown timezone 'Nowhere/City': expected an IANA name such as 'Europe/London'"),
    ("availability", {"action": "find_slots", "time_min": "2026-11-16", "time_max": "2026-11-16",
                      "duration_minutes": 30, "timezone": "Mars/Olympus"},
     "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"),
    ("availability", {"action": "query", "time_min": "2026-11-16", "time_max": "2026-11-16",
                      "timezone": "Mars/Olympus"},
     "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"),
    ("weekly_brief", {"start_date": "13/11/2026"},
     "Invalid start_date '13/11/2026': expected a date such as '2026-11-16'"),
    ("weekly_brief", {"timezone": "Mars/Olympus"},
     "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"),
]


@pytest.mark.parametrize("name, arguments, message", INPUT_ERRORS,
                         ids=[f"{n}-{i}" for i, (n, _, _) in enumerate(INPUT_ERRORS)])
async def test_an_input_error_is_answered_plainly_and_logged_without_a_traceback(
        fake, records, name, arguments, message):
    is_error, text = await _call(name, arguments)

    assert is_error
    assert text == message
    assert fake.calls == [], "the request reached Google"
    logged = [r for r in records if r.getMessage() == f"Error calling tool {name!r}"]
    assert len(logged) == 1, [r.getMessage() for r in records]
    assert logged[0].levelno == logging.INFO
    assert not logged[0].exc_info


@pytest.mark.parametrize("arguments, start", [
    ({"action": "list", "account": "nope"}, "Account 'nope' not found."),
    ({"action": "list"}, "No account specified and no default account configured."),
])
async def test_an_unknown_or_missing_account_is_an_input_error(records, arguments, start):
    # No fake service: the real account lookup runs against an empty local config.
    is_error, text = await _call("calendars", arguments)

    assert is_error
    assert text.startswith(start)
    logged = [r for r in records if r.getMessage() == "Error calling tool 'calendars'"]
    assert [(r.levelno, bool(r.exc_info)) for r in logged] == [(logging.INFO, False)]


async def test_a_series_rule_on_one_occurrence_is_an_input_error(fake, records):
    fake.respond("events", "get", {"id": "e1", "recurringEventId": "s1",
                                   "start": {"dateTime": "2026-11-17T10:00:00+02:00"},
                                   "end": {"dateTime": "2026-11-17T11:00:00+02:00"}})

    is_error, text = await _call("events", {"action": "update", "event_id": "e1",
                                            "recurrence": ["RRULE:FREQ=DAILY"]})

    assert is_error
    assert text == "recurrence belongs to the series; pass scope='all'"
    assert [(r, m) for r, m, _ in fake.calls] == [("events", "get")]
    logged = [r for r in records if r.getMessage() == "Error calling tool 'events'"]
    assert [(r.levelno, bool(r.exc_info)) for r in logged] == [(logging.INFO, False)]


async def test_a_failure_of_the_server_keeps_error_and_the_traceback(fake, records):
    fake.respond("events", "list", RuntimeError("boom"))

    is_error, text = await _call("events", {"action": "list", "time_min": "2026-11-16",
                                            "timezone": "Europe/London"})

    assert is_error
    assert "boom" in text
    logged = [r for r in records if r.getMessage() == "Error calling tool 'events'"]
    assert [(r.levelno, bool(r.exc_info)) for r in logged] == [(logging.ERROR, True)]


async def test_a_new_timezone_for_an_event_is_checked_before_the_update(fake, records):
    fake.respond("events", "get", {"id": "e1", "start": {"dateTime": "2026-11-17T10:00:00+02:00"},
                                   "end": {"dateTime": "2026-11-17T11:00:00+02:00"}})

    is_error, text = await _call("events", {"action": "update", "event_id": "e1",
                                            "timezone": "Mars/Olympus"})

    assert is_error
    assert text == "Unknown timezone 'Mars/Olympus': expected an IANA name such as 'Europe/London'"
    assert {(r, m) for r, m, _ in fake.calls} == {("events", "get")}
    logged = [r for r in records if r.getMessage() == "Error calling tool 'events'"]
    assert [(r.levelno, bool(r.exc_info)) for r in logged] == [(logging.INFO, False)]


async def test_responding_to_an_event_one_is_not_invited_to_is_an_input_error(
        fake, records, monkeypatch):
    import google_calendar.tools.attendees as tools_attendees

    monkeypatch.setattr(tools_attendees, "get_authorized_email", lambda account: "me@example.test")
    fake.respond("events", "get", {"id": "e1", "attendees": [{"email": "other@example.test"}]})

    is_error, text = await _call("attendees", {"action": "respond", "event_id": "e1",
                                               "response": "accepted"})

    assert is_error
    assert text.startswith("You (me@example.test) are not an attendee of this event.")
    assert {(r, m) for r, m, _ in fake.calls} == {("events", "get")}
    logged = [r for r in records if r.getMessage() == "Error calling tool 'attendees'"]
    assert [(r.levelno, bool(r.exc_info)) for r in logged] == [(logging.INFO, False)]


@pytest.mark.parametrize("name", ["Mars/Olympus", "../../etc/passwd", ""])
def test_zone_refuses_any_name_zoneinfo_refuses(name):
    from google_calendar.errors import InputError, zone

    with pytest.raises(InputError, match="Unknown timezone"):
        zone(name)


def test_an_unknown_action_is_an_input_error():
    # The MCP schema already refuses an action outside each tool's list; a direct call
    # (another module, a future caller) gets the same InputError.
    from google_calendar.errors import InputError
    from google_calendar.tools.attendees import attendees
    from google_calendar.tools.availability import availability
    from google_calendar.tools.calendars import calendars
    from google_calendar.tools.events import events

    for call in (lambda: events(action="nope"), lambda: calendars(action="nope"),
                 lambda: attendees(action="nope", event_id="e1"),
                 lambda: availability(action="nope")):
        with pytest.raises(InputError):
            call()


def test_an_input_error_is_still_a_value_error():
    # Code that catches ValueError (per-operation results in projects/contacts and
    # events batch) keeps catching it.
    from google_calendar.errors import InputError

    assert issubclass(InputError, ValueError)
