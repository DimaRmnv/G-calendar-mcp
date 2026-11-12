"""Calendar tools against a fake Google service: time zones, retries, paging, recurrence.

Issue #3. Every test drives a tool the MCP client calls (the shipped path), with the
Google service replaced at each module's `get_service` seam. The account timezone is
served by the fake `settings().get` exactly as Google answers it, so the tools resolve
it the real way.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import http.client

import httplib2
import pytest
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

import google_calendar.api.calendars as api_calendars
import google_calendar.api.client as client
import google_calendar.api.events as api_events
import google_calendar.api.freebusy as api_freebusy
import google_calendar.tools.calendars as tools_calendars
import google_calendar.tools.events as tools_events
import google_calendar.tools.projects.report as report
from google_calendar.settings import settings
from google_calendar.tools.attendees import attendees
from google_calendar.tools.availability import availability
from google_calendar.tools.calendars import calendars
from google_calendar.tools.events import events
from google_calendar.tools.intelligence import weekly_brief

LOCAL_ZONE = "Africa/Johannesburg"  # +02:00 all year, no DST
SERIES_RULE = ["RRULE:FREQ=WEEKLY;BYDAY=TU"]
TEAM_CALENDAR = "team@group.calendar.google.com"
BASE_URL = "https://stand.example/calendar/mcp"
AUTH_URL = f"{BASE_URL}/oauth/start/work"


# --------------------------------------------------------------------------
# Fake Google service
# --------------------------------------------------------------------------

class FakeService:
    """`service.<resource>().<method>(**params).execute()` with scripted outcomes.

    Outcomes per (resource, method) are consumed in order; the last one repeats.
    An outcome is a response dict, an exception to raise, or a callable(params).
    """

    def __init__(self):
        self.queues = defaultdict(list)
        self.calls = []        # (resource, method, params) per request built
        self.executions = []   # (resource, method) per execute()
        self.sleeps = []

    def respond(self, resource, method, *outcomes):
        self.queues[(resource, method)] = list(outcomes)

    def params(self, resource, method):
        return [p for r, m, p in self.calls if (r, m) == (resource, method)]

    def executed(self, resource, method):
        return self.executions.count((resource, method))

    def __getattr__(self, resource):
        return lambda: _Resource(self, resource)


class _Resource:
    def __init__(self, svc, name):
        self.svc, self.name = svc, name

    def __getattr__(self, method):
        def build(**params):
            self.svc.calls.append((self.name, method, params))
            return _Request(self.svc, (self.name, method), params)
        return build


class _Request:
    def __init__(self, svc, key, params):
        self.svc, self.key, self.params = svc, key, params

    def execute(self, **_):
        self.svc.executions.append(self.key)
        queue = self.svc.queues[self.key]
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome(self.params) if callable(outcome) else outcome


def http_error(status, reason, message="error from Google", details=None, body=None):
    if body is None:
        body = {"error": {"code": status, "message": message,
                          "errors": [{"domain": "global", "reason": reason, "message": message}]}}
        if details is not None:
            body["error"]["details"] = details
    return HttpError(httplib2.Response({"status": str(status)}), json.dumps(body).encode())


def event(event_id, start="2026-11-12T12:00:00+02:00", end="2026-11-12T14:00:00+02:00", **extra):
    return {"id": event_id, "summary": event_id, "start": {"dateTime": start},
            "end": {"dateTime": end}, **extra}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))  # empty local config: no default account
    monkeypatch.setattr(settings, "server_base_url", BASE_URL, raising=False)
    svc = FakeService()
    svc.respond("settings", "get", {"value": LOCAL_ZONE})
    for module in (api_events, api_freebusy, api_calendars, client, tools_calendars, report):
        monkeypatch.setattr(module, "get_service", lambda account=None: svc, raising=False)
    monkeypatch.setattr(client.time, "sleep", svc.sleeps.append)
    return svc


# --------------------------------------------------------------------------
# 1. Naive times are local to the account, not UTC
# --------------------------------------------------------------------------

def test_naive_window_is_read_in_the_account_timezone(fake):
    fake.respond("events", "list", {"items": [event("training")]})

    result = events(action="list", account="work",
                    time_min="2026-11-12T12:00:00", time_max="2026-11-12T14:00:00")

    sent = fake.params("events", "list")[-1]
    assert (sent["timeMin"], sent["timeMax"]) == ("2026-11-12T12:00:00+02:00",
                                                  "2026-11-12T14:00:00+02:00")
    assert [e["id"] for e in result["events"]] == ["training"]


def test_explicit_timezone_wins_over_the_account_timezone(fake):
    fake.respond("events", "list", {"items": []})

    events(action="list", account="work", timezone="Asia/Bangkok",
           time_min="2026-11-12T12:00:00", time_max="2026-11-12T14:00:00")

    assert fake.params("events", "list")[-1]["timeMin"] == "2026-11-12T12:00:00+07:00"


def test_offset_given_by_the_caller_is_kept(fake):
    fake.respond("events", "list", {"items": []})

    events(action="list", account="work",
           time_min="2026-11-12T10:00:00Z", time_max="2026-11-12T14:00:00+05:00")

    sent = fake.params("events", "list")[-1]
    assert (sent["timeMin"], sent["timeMax"]) == ("2026-11-12T10:00:00+00:00",
                                                  "2026-11-12T14:00:00+05:00")


def test_period_today_is_the_calendar_day_of_the_account(fake):
    fake.respond("settings", "get", {"value": "Asia/Bangkok"})  # no DST: offset is fixed
    fake.respond("events", "list", {"items": []})

    events(action="list", account="work", period="today")

    sent = fake.params("events", "list")[-1]
    t_min, t_max = datetime.fromisoformat(sent["timeMin"]), datetime.fromisoformat(sent["timeMax"])
    assert sent["timeMin"].endswith("T00:00:00+07:00")
    assert t_max - t_min == timedelta(days=1)
    assert t_min.date() == datetime.now(ZoneInfo("Asia/Bangkok")).date()


def test_only_time_min_opens_a_seven_day_window_from_it(fake):
    fake.respond("events", "list", {"items": []})

    events(action="list", account="work", time_min="2026-11-20T00:00:00")

    sent = fake.params("events", "list")[-1]
    assert (sent["timeMin"], sent["timeMax"]) == ("2026-11-20T00:00:00+02:00",
                                                  "2026-11-27T00:00:00+02:00")


def test_only_time_max_closes_a_seven_day_window_on_it(fake):
    fake.respond("events", "list", {"items": []})

    events(action="list", account="work", time_max="2026-11-20T00:00:00")

    sent = fake.params("events", "list")[-1]
    assert (sent["timeMin"], sent["timeMax"]) == ("2026-11-13T00:00:00+02:00",
                                                  "2026-11-20T00:00:00+02:00")


def test_search_reads_naive_bounds_in_the_account_timezone(fake):
    fake.respond("events", "list", {"items": []})

    events(action="search", account="work", query="x",
           time_min="2026-11-12T12:00:00", time_max="2026-11-12T14:00:00")

    sent = fake.params("events", "list")[-1]
    assert (sent["timeMin"], sent["timeMax"]) == ("2026-11-12T12:00:00+02:00",
                                                  "2026-11-12T14:00:00+02:00")


def test_search_honours_an_explicit_timezone(fake):
    fake.respond("events", "list", {"items": []})

    events(action="search", account="work", query="x", timezone="Asia/Bangkok",
           time_min="2026-11-12T12:00:00", time_max="2026-11-12T14:00:00")

    assert fake.params("events", "list")[-1]["timeMin"] == "2026-11-12T12:00:00+07:00"


FROZEN_NOW = datetime(2026, 11, 12, 15, 30, tzinfo=ZoneInfo("UTC"))  # 17:30 at +02:00


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW.astimezone(tz) if tz else FROZEN_NOW.replace(tzinfo=None)


@pytest.fixture
def frozen_now(monkeypatch):
    monkeypatch.setattr(tools_events, "datetime", _FrozenDatetime)


@pytest.mark.parametrize("bound, expected", [
    # "since X" in the past: up to a year past today — never less than without a bound.
    ({"time_min": "2025-03-01T00:00:00"}, ("2025-03-01T00:00:00+02:00", "2027-11-12T17:30:00+02:00")),
    # "since X" beyond the default window: a year past X, never inverted.
    ({"time_min": "2028-06-01T00:00:00"}, ("2028-06-01T00:00:00+02:00", "2029-06-01T00:00:00+02:00")),
    # "until X" in the future: from a year before today.
    ({"time_max": "2030-01-01T00:00:00"}, ("2025-11-12T17:30:00+02:00", "2030-01-01T00:00:00+02:00")),
    # "until X" before the default window: a year before X, never inverted.
    ({"time_max": "2020-06-01T00:00:00"}, ("2019-06-02T00:00:00+02:00", "2020-06-01T00:00:00+02:00")),
    # no bound: a year either side of now.
    ({}, ("2025-11-12T17:30:00+02:00", "2027-11-12T17:30:00+02:00")),
])
def test_search_window_covers_today_plus_a_year_and_never_inverts(fake, frozen_now, bound, expected):
    fake.respond("events", "list", {"items": []})

    events(action="search", account="work", query="x", **bound)

    sent = fake.params("events", "list")[-1]
    assert (sent["timeMin"], sent["timeMax"]) == expected


def test_list_without_bounds_covers_the_next_seven_days(fake, frozen_now):
    fake.respond("events", "list", {"items": []})

    events(action="list", account="work")

    sent = fake.params("events", "list")[-1]
    assert (sent["timeMin"], sent["timeMax"]) == ("2026-11-12T17:30:00+02:00",
                                                  "2026-11-19T17:30:00+02:00")


def test_freebusy_query_reads_a_naive_window_in_the_account_timezone(fake):
    fake.respond("freebusy", "query", {"calendars": {"primary": {"busy": []}}})

    availability(action="query", account="work",
                 time_min="2026-11-12T12:00:00", time_max="2026-11-12T14:00:00")

    body = fake.params("freebusy", "query")[-1]["body"]
    assert (body["timeMin"], body["timeMax"]) == ("2026-11-12T12:00:00+02:00",
                                                  "2026-11-12T14:00:00+02:00")


# --------------------------------------------------------------------------
# 2. Retries and error classification (execute_with_retry on every call)
# --------------------------------------------------------------------------

def test_rate_limited_read_is_retried(fake):
    fake.respond("events", "get", http_error(429, "rateLimitExceeded"), event("e1"))

    result = events(action="get", account="work", event_id="e1")

    assert result["id"] == "e1"
    assert fake.executed("events", "get") == 2


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_error_on_a_read_is_retried(fake, status):
    fake.respond("events", "get", http_error(status, "backendError"), event("e1"))

    assert events(action="get", account="work", event_id="e1")["id"] == "e1"
    assert fake.executed("events", "get") == 2


@pytest.mark.parametrize("failure", [
    ConnectionResetError("reset by peer"),
    http.client.IncompleteRead(b"partial"),
    httplib2.ServerNotFoundError("Unable to find the server"),
])
def test_network_error_on_a_read_is_retried(fake, failure):
    fake.respond("events", "get", failure, event("e1"))

    assert events(action="get", account="work", event_id="e1")["id"] == "e1"
    assert fake.executed("events", "get") == 2


def test_unauthorized_is_answered_with_an_auth_url(fake):
    fake.respond("events", "get", http_error(401, "authError", "Invalid Credentials"))

    result = events(action="get", account="work", event_id="e1")

    assert (result["error"], result["auth_url"]) == ("auth_required", AUTH_URL)


def test_insufficient_scope_is_answered_with_an_auth_url(fake):
    fake.respond("events", "get", http_error(
        403, "insufficientPermissions", "Request had insufficient authentication scopes."))

    result = events(action="get", account="work", event_id="e1")

    assert (result["error"], result["auth_url"]) == ("auth_required", AUTH_URL)


def test_insufficient_scope_named_only_in_details_is_an_auth_problem(fake):
    fake.respond("events", "get", http_error(
        403, "forbidden", "Request had insufficient authentication scopes.",
        details=[{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                  "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]))

    result = events(action="get", account="work", event_id="e1")

    assert (result["error"], result["auth_url"]) == ("auth_required", AUTH_URL)


@pytest.mark.parametrize("failure", [
    http_error(401, "authError", "Invalid Credentials"),
    http_error(403, "insufficientPermissions", "Request had insufficient authentication scopes."),
    RefreshError("invalid_grant: Token has been expired or revoked."),
])
def test_an_auth_failure_drops_the_cached_service(fake, monkeypatch, failure):
    monkeypatch.setitem(client._services, "work", object())
    fake.respond("events", "get", failure)

    result = events(action="get", account="work", event_id="e1")

    assert (result["error"], result["auth_url"]) == ("auth_required", AUTH_URL)
    assert "work" not in client._services


@pytest.mark.parametrize("reason", ["quotaExceeded", "dailyLimitExceeded"])
def test_an_exhausted_quota_is_not_retried(fake, reason):
    # Unlike a rate limit, an exhausted quota does not clear within seconds: retrying
    # only multiplies the calls.
    fake.respond("events", "get", http_error(403, reason), event("e1"))

    with pytest.raises(HttpError):
        events(action="get", account="work", event_id="e1")

    assert fake.executed("events", "get") == 1


def test_user_rate_limit_403_is_retried(fake):
    fake.respond("events", "get", http_error(403, "userRateLimitExceeded"), event("e1"))

    assert events(action="get", account="work", event_id="e1")["id"] == "e1"
    assert fake.executed("events", "get") == 2


def test_a_rate_limit_that_persists_ends_in_a_rate_limit_error(fake):
    fake.respond("events", "get", http_error(429, "rateLimitExceeded"))

    with pytest.raises(client.RateLimitError):
        events(action="get", account="work", event_id="e1")

    assert fake.executed("events", "get") == 3
    assert fake.sleeps == [2, 4]


@pytest.mark.parametrize("body", [
    {"error": {"code": 403, "errors": "not-a-list"}},
    {"error": {"code": 403, "errors": 5}},
    {"error": {"code": 403, "errors": {"reason": "insufficientPermissions"}}},
    {"error": {"code": 403, "details": [{"reason": ["insufficientPermissions"]}]}},
    {"error": "a string"},
    ["not", "an", "object"],
])
def test_a_malformed_error_body_still_surfaces_googles_error(fake, body):
    fake.respond("events", "get", http_error(403, None, body=body))

    with pytest.raises(HttpError):
        events(action="get", account="work", event_id="e1")


def test_a_token_refresh_transport_failure_is_retried_even_for_create(fake):
    # google-auth raises TransportError only while refreshing the token, before the
    # API request is sent (or after Google refused it with 401): nothing was created.
    fake.respond("events", "insert", TransportError("token endpoint unreachable"),
                 lambda params: event(params["body"]["id"]))

    result = events(action="create", account="work", summary="x",
                    start="2026-11-12T12:00:00", end="2026-11-12T13:00:00")

    assert result["id"] == fake.params("events", "insert")[0]["body"]["id"]
    assert fake.executed("events", "insert") == 2


def test_forbidden_for_a_non_organizer_is_not_an_auth_problem(fake):
    fake.respond("events", "get", event("e1"))
    fake.respond("events", "patch", http_error(
        403, "forbiddenForNonOrganizer", "Shared properties can only be changed by the organizer."))

    with pytest.raises(HttpError) as raised:
        events(action="update", account="work", event_id="e1", summary="renamed")

    assert raised.value.resp.status == 403
    assert "organizer" in str(raised.value)
    assert fake.executed("events", "patch") == 1


def test_rate_limit_403_on_create_is_retried(fake):
    fake.respond("events", "insert", http_error(403, "rateLimitExceeded"), event("new"))

    result = events(action="create", account="work", summary="x",
                    start="2026-11-12T12:00:00", end="2026-11-12T13:00:00")

    assert result["id"] == "new"
    assert fake.executed("events", "insert") == 2


@pytest.mark.parametrize("failure", [ConnectionResetError("reset by peer"),
                                     http_error(503, "backendError")])
def test_create_is_not_retried_after_a_lost_or_failed_response(fake, failure):
    # The insert may have happened server-side; repeating it would create a duplicate.
    fake.respond("events", "insert", failure, event("dup"))

    with pytest.raises(type(failure)):
        events(action="create", account="work", summary="x",
               start="2026-11-12T12:00:00", end="2026-11-12T13:00:00")

    assert fake.executed("events", "insert") == 1


def test_create_sends_its_own_event_id(fake):
    fake.respond("events", "insert", lambda params: event(params["body"]["id"]))

    events(action="create", account="work", summary="x",
           start="2026-11-12T12:00:00", end="2026-11-12T13:00:00")

    sent_id = fake.params("events", "insert")[0]["body"]["id"]
    assert re.fullmatch(r"[0-9a-v]{5,1024}", sent_id)  # Google's rule for client ids


def test_create_whose_transport_resend_hits_a_duplicate_returns_the_event(fake):
    # httplib2 re-sends a request once when the connection drops before the response;
    # if Google had created the event, the re-send answers 409 for our own id.
    fake.respond("events", "insert", http_error(409, "duplicate", "The requested identifier already exists."))
    fake.respond("events", "get", lambda params: event(params["eventId"]))

    result = events(action="create", account="work", summary="x", calendar_id=TEAM_CALENDAR,
                    start="2026-11-12T12:00:00", end="2026-11-12T13:00:00")

    sent_id = fake.params("events", "insert")[0]["body"]["id"]
    assert result["id"] == sent_id
    looked_up = fake.params("events", "get")[-1]
    assert (looked_up["eventId"], looked_up["calendarId"]) == (sent_id, TEAM_CALENDAR)


def test_move_is_not_retried_after_a_lost_response(fake):
    fake.respond("events", "get", event("e1"))
    fake.respond("events", "move", ConnectionResetError("reset by peer"), event("e1"))

    with pytest.raises(ConnectionResetError):
        events(action="update", account="work", event_id="e1", destination_calendar_id="other")

    assert fake.executed("events", "move") == 1


def test_quick_add_is_not_retried_after_a_lost_response(fake):
    fake.respond("events", "quickAdd", ConnectionResetError("reset by peer"), event("q"))

    with pytest.raises(ConnectionResetError):
        api_events.quick_add("lunch tomorrow at noon", account="work")

    assert fake.executed("events", "quickAdd") == 1


@pytest.mark.parametrize("action, method, extra", [
    ("create", "insert", {"summary": "Project X"}),
    ("delete", "delete", {"calendar_id": "c1@group.calendar.google.com"}),
])
def test_calendar_create_and_delete_are_not_retried_after_a_lost_response(fake, action, method, extra):
    fake.respond("calendars", method, ConnectionResetError("reset by peer"), {"id": "c1"})

    with pytest.raises(ConnectionResetError):
        calendars(action=action, account="work", **extra)

    assert fake.executed("calendars", method) == 1


def test_delete_retried_after_a_lost_response_reports_the_deletion(fake):
    # First attempt deleted the event but the response was lost; the retry sees 410.
    fake.respond("events", "get", event("e1"))
    fake.respond("events", "delete", ConnectionResetError("reset by peer"),
                 http_error(410, "deleted", "Resource has been deleted"))

    result = events(action="delete", account="work", event_id="e1")

    assert result["deleted"] is True
    assert fake.executed("events", "delete") == 2


def test_delete_of_an_unknown_event_still_fails(fake):
    fake.respond("events", "get", event("e1"))
    fake.respond("events", "delete", http_error(404, "notFound", "Not Found"))

    with pytest.raises(HttpError):
        events(action="delete", account="work", event_id="e1")


def test_settings_do_not_swallow_an_auth_error(fake):
    fake.respond("settings", "get", http_error(401, "authError", "Invalid Credentials"))

    result = calendars(action="settings", account="work")

    assert (result["error"], result["auth_url"]) == ("auth_required", AUTH_URL)


def test_settings_skip_only_a_setting_google_does_not_have(fake):
    def serve(params):
        if params["setting"] == "locale":
            raise http_error(404, "notFound", "Not Found")
        return {"value": LOCAL_ZONE if params["setting"] == "timezone" else "x"}
    fake.respond("settings", "get", serve)

    result = calendars(action="settings", account="work")

    assert result["timezone"] == LOCAL_ZONE
    assert "locale" not in result


def test_settings_surface_any_other_google_error(fake):
    fake.respond("settings", "get", http_error(403, "forbidden", "Forbidden"))

    with pytest.raises(HttpError):
        calendars(action="settings", account="work")


def test_respond_answers_auth_required_when_the_identity_lookup_is_refused(fake):
    fake.respond("settings", "get", http_error(401, "authError", "Invalid Credentials"))

    result = attendees(action="respond", account="work", event_id="e1", response="accepted")

    assert (result["error"], result["auth_url"]) == ("auth_required", AUTH_URL)


def test_a_failed_timezone_lookup_is_not_replaced_by_utc(fake):
    fake.respond("settings", "get", http_error(500, "backendError"))
    fake.respond("events", "list", {"items": []})

    with pytest.raises(HttpError):
        events(action="list", account="work",
               time_min="2026-11-12T12:00:00", time_max="2026-11-12T14:00:00")

    assert fake.params("events", "list") == []


def test_bounds_with_offsets_do_not_need_the_account_timezone(fake):
    fake.respond("settings", "get", http_error(403, "forbidden", "Forbidden"))
    fake.respond("events", "list", {"items": [event("a")]})

    listed = events(action="list", account="work",
                    time_min="2026-11-12T10:00:00Z", time_max="2026-11-12T14:00:00Z")
    found = events(action="search", account="work", query="a",
                   time_min="2026-11-12T10:00:00Z", time_max="2026-11-12T14:00:00Z")

    assert [e["id"] for e in listed["events"]] == ["a"] == [e["id"] for e in found["events"]]
    assert fake.executed("settings", "get") == 0


# --------------------------------------------------------------------------
# events(batch): the second surface of create/update/delete
# --------------------------------------------------------------------------

def _three_creates():
    return [{"action": "create", "summary": f"op{i}",
             "start": "2026-11-12T12:00:00", "end": "2026-11-12T13:00:00"} for i in range(3)]


def test_batch_answers_auth_required_and_stops(fake):
    fake.respond("events", "insert", http_error(401, "authError", "Invalid Credentials"))

    result = events(action="batch", account="work", operations=_three_creates())

    assert (result["error"], result["auth_url"]) == ("auth_required", AUTH_URL)
    assert [r["status"] for r in result["results"]] == ["error", "not_attempted", "not_attempted"]
    assert fake.executed("events", "insert") == 1


def test_batch_stops_when_the_rate_limit_persists(fake):
    fake.respond("events", "insert", http_error(429, "rateLimitExceeded"))

    result = events(action="batch", account="work", operations=_three_creates())

    assert [r["status"] for r in result["results"]] == ["error", "not_attempted", "not_attempted"]
    assert [r["index"] for r in result["results"]] == [0, 1, 2]
    assert "rate limit" in result["stopped"].lower()
    assert fake.executed("events", "insert") == 3


def test_batch_stops_when_the_token_has_expired(fake, monkeypatch):
    def expired(account=None):
        raise client.TokenExpiredError(account="work", auth_url=AUTH_URL)
    monkeypatch.setattr(api_events, "get_service", expired)

    result = events(action="batch", account="work", operations=_three_creates())

    assert (result["error"], result["auth_url"]) == ("token_expired", AUTH_URL)
    assert [r["status"] for r in result["results"]] == ["error", "not_attempted", "not_attempted"]


def test_batch_keeps_going_after_an_ordinary_error(fake):
    fake.respond("events", "insert", http_error(400, "invalid", "Bad Request"),
                 lambda params: event(params["body"]["id"]))

    result = events(action="batch", account="work", operations=_three_creates())

    assert [r["status"] for r in result["results"]] == ["error", "success", "success"]


# --------------------------------------------------------------------------
# 3. Paging
# --------------------------------------------------------------------------

def _paged(pages):
    """events.list outcome serving `pages` = {pageToken: (items, next_token)}."""
    def serve(params):
        items, nxt = pages[params.get("pageToken")]
        return {"items": items, **({"nextPageToken": nxt} if nxt else {})}
    return serve


def test_list_hands_out_the_next_page_token_and_accepts_it_back(fake):
    fake.respond("events", "list", _paged({None: ([event("a")], "p2"), "p2": ([event("b")], None)}))
    window = {"time_min": "2026-11-09T00:00:00", "time_max": "2026-11-13T00:00:00"}

    first = events(action="list", account="work", max_results=1, **window)
    second = events(action="list", account="work", max_results=1, page_token="p2", **window)

    assert (first["hasMore"], first["nextPageToken"]) == (True, "p2")
    assert [e["id"] for e in second["events"]] == ["b"]
    assert (second["hasMore"], second.get("nextPageToken")) == (False, None)


def test_search_hands_out_the_next_page_token(fake):
    fake.respond("events", "list", _paged({None: ([event("a")], "p2")}))

    result = events(action="search", account="work", query="a", max_results=1)

    assert result["nextPageToken"] == "p2"


@pytest.mark.parametrize("action, extra", [("list", {}), ("search", {"query": "a"})])
def test_the_window_queried_is_returned_for_the_next_page(fake, action, extra):
    # A default window is computed from "now"; the next page must reuse it, not a new one.
    fake.respond("events", "list", _paged({None: ([event("a")], "p2")}))

    result = events(action=action, account="work", max_results=1, **extra)

    sent = fake.params("events", "list")[-1]
    assert (result["timeMin"], result["timeMax"]) == (sent["timeMin"], sent["timeMax"])


@pytest.fixture
def report_stand(monkeypatch):
    """generate_report with the database and Excel steps stubbed; records parsed ids."""
    seen = []

    async def nothing(*_, **__):
        return None

    async def record(evts):
        seen.extend(e["id"] for e in evts)
        return []

    class _Conn:
        async def execute(self, *_):
            return None

    class _Db:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *_):
            return False

    for name in ("ensure_database", "config_get", "norm_get"):
        monkeypatch.setattr(report, name, nothing)
    monkeypatch.setattr(report, "parse_events_batch", record)
    monkeypatch.setattr(report, "_create_excel_file", lambda *_, **__: None)
    monkeypatch.setattr(report, "get_db", _Db)
    return seen


async def test_time_tracking_report_reads_every_page_within_account_month(fake, report_stand):
    fake.respond("settings", "get", {"value": "Asia/Bangkok"})
    fake.respond("events", "list", _paged({
        None: ([event(f"p1-{i}") for i in range(3)], "p2"),
        "p2": ([event(f"p2-{i}") for i in range(2)], None),
    }))

    await report.generate_report(report_type="status", account="work")

    assert report_stand == ["p1-0", "p1-1", "p1-2", "p2-0", "p2-1"]
    now = datetime.now(ZoneInfo("Asia/Bangkok"))
    assert fake.params("events", "list")[0]["timeMin"] == f"{now:%Y-%m}-01T00:00:00+07:00"


async def test_custom_report_bounds_are_whole_days_in_the_account_timezone(fake, report_stand):
    fake.respond("events", "list", {"items": []})

    await report.generate_report(report_type="custom", account="work",
                                 start_date="2026-10-01", end_date="2026-10-31")

    sent = fake.params("events", "list")[0]
    assert (sent["timeMin"], sent["timeMax"]) == ("2026-10-01T00:00:00+02:00",
                                                  "2026-10-31T23:59:59+02:00")


@pytest.mark.parametrize("report_type, first_day", [
    ("month", lambda now: now.replace(day=1)),
    ("week", lambda now: now - timedelta(days=now.weekday())),
])
async def test_month_and_week_report_bounds_start_at_local_midnight(
        fake, report_stand, report_type, first_day):
    fake.respond("settings", "get", {"value": "Asia/Bangkok"})
    fake.respond("events", "list", {"items": []})

    await report.generate_report(report_type=report_type, account="work")

    start = first_day(datetime.now(ZoneInfo("Asia/Bangkok")))
    assert fake.params("events", "list")[0]["timeMin"] == f"{start:%Y-%m-%d}T00:00:00+07:00"


@pytest.mark.parametrize("report_type", ["status", "week"])
async def test_report_backoff_does_not_block_the_event_loop(fake, report_stand, monkeypatch, report_type):
    # A sleep on the event-loop thread freezes every other MCP session and /health.
    on_loop = []

    def sleep(seconds):
        try:
            asyncio.get_running_loop()
            on_loop.append(seconds)
        except RuntimeError:
            pass

    monkeypatch.setattr(client.time, "sleep", sleep)
    fake.respond("settings", "get", http_error(429, "rateLimitExceeded"), {"value": LOCAL_ZONE})
    fake.respond("events", "list", http_error(429, "rateLimitExceeded"), {"items": []})

    await report.generate_report(report_type=report_type, account="work")

    assert fake.executed("events", "list") == 2
    assert on_loop == []


def test_weekly_brief_reads_every_page(fake):
    fake.respond("events", "list", _paged({
        None: ([event(f"p1-{i}") for i in range(3)], "p2"),
        "p2": ([event(f"p2-{i}") for i in range(2)], None),
    }))

    result = weekly_brief(account="work", start_date="2026-11-09")

    assert result["summary"]["total_events"] == 5


# --------------------------------------------------------------------------
# 4. Recurrence on update
# --------------------------------------------------------------------------

def test_update_changes_the_rule_of_a_series(fake):
    fake.respond("events", "get", event("series", recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO"]))
    fake.respond("events", "patch", event("series", recurrence=SERIES_RULE))

    events(action="update", account="work", event_id="series", recurrence=SERIES_RULE, scope="all")

    patch = fake.params("events", "patch")[-1]
    assert (patch["eventId"], patch["body"]["recurrence"]) == ("series", SERIES_RULE)


def test_update_turns_a_single_event_into_a_series(fake):
    fake.respond("events", "get", event("one"))
    fake.respond("events", "patch", event("one", recurrence=SERIES_RULE))

    events(action="update", account="work", event_id="one", recurrence=SERIES_RULE)

    assert fake.params("events", "patch")[-1]["body"]["recurrence"] == SERIES_RULE


def test_recurrence_for_a_single_occurrence_is_refused(fake):
    fake.respond("events", "get", event("series", recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO"]))

    with pytest.raises(ValueError, match="recurrence belongs to the series; pass scope='all'"):
        events(action="update", account="work", event_id="series",
               recurrence=SERIES_RULE, scope="single")

    assert fake.params("events", "patch") == []


def test_recurrence_sent_with_an_occurrence_id_is_refused(fake):
    fake.respond("events", "get", event("series_20261117T100000Z", recurringEventId="series"))

    with pytest.raises(ValueError, match="recurrence belongs to the series; pass scope='all'"):
        events(action="update", account="work", event_id="series_20261117T100000Z",
               recurrence=SERIES_RULE)

    assert fake.params("events", "patch") == []


# --------------------------------------------------------------------------
# 5. find_slots and calendars it could not read
# --------------------------------------------------------------------------

UNREADABLE = "someone-else@group.calendar.google.com"


def test_find_slots_names_the_calendars_it_could_not_check(fake):
    fake.respond("freebusy", "query", {"calendars": {
        "primary": {"busy": []},
        UNREADABLE: {"busy": [], "errors": [{"domain": "global", "reason": "notFound"}]},
    }})

    result = availability(action="find_slots", account="work", duration_minutes=60,
                          time_min="2026-11-16", time_max="2026-11-16",
                          calendars=["primary", UNREADABLE], max_slots=2)

    assert result["unchecked_calendars"] == {UNREADABLE: ["notFound"]}
    assert UNREADABLE in result["warning"]
    assert result["total_found"] == 2


def test_find_slots_without_errors_carries_no_warning(fake):
    fake.respond("freebusy", "query", {"calendars": {"primary": {"busy": []}}})

    result = availability(action="find_slots", account="work", duration_minutes=60,
                          time_min="2026-11-16", time_max="2026-11-16", max_slots=2)

    assert result["unchecked_calendars"] == {}
    assert "warning" not in result


def test_find_slots_names_a_calendar_missing_from_googles_answer(fake):
    fake.respond("freebusy", "query", {"calendars": {"primary": {"busy": []}}})

    result = availability(action="find_slots", account="work", duration_minutes=60,
                          time_min="2026-11-16", time_max="2026-11-16",
                          calendars=["primary", UNREADABLE], max_slots=2)

    assert result["unchecked_calendars"] == {UNREADABLE: ["missingFromResponse"]}
    assert UNREADABLE in result["warning"]
