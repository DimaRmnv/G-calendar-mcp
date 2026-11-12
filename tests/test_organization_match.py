"""contacts: every organization filter matches the organization's name, short name or local name.

Issue #9. `contact_list(organization="ADB")` found nobody although the organization
"Asian Development Bank" (short name ADB) has contacts. contact_list, export_contacts
and the organization report each had their own copy of the SQL, all matching part of
the full name only; contact_resolve's context compared a key the contact record does
not have, so that hint never applied. Now all four use one rule, `database.ORG_MATCH`:
part of the name, short name or local name, any case. The tests record the SQL sent.
"""
from __future__ import annotations

import pytest

import google_calendar.tools.contacts.database as database
import google_calendar.tools.contacts.lookup as lookup
import google_calendar.tools.contacts.manage as manage
import google_calendar.tools.contacts.report as report

ORG_RULE = ("organization_id IN (SELECT id FROM organizations WHERE name ILIKE $1 "
            "OR short_name ILIKE $1 OR name_local ILIKE $1)")


class _Sent(list):
    """The (query, params) pairs sent, plus the stub's `state`."""

    state: dict


class _Stop(Exception):
    """Ends an operation after its first query, so nothing is written."""


@pytest.fixture
def sql(monkeypatch):
    """Database stubbed at the connection; returns the list of (query, params) sent.

    Organization-id lookups answer `org_ids`; with `stop` set, any other query ends
    the operation after it is recorded.
    """
    sent = _Sent()
    state = sent.state = {"org_ids": [], "stop": False}

    class Conn:
        async def fetch(self, query, *params):
            query = " ".join(query.split())
            sent.append((query, params))
            if query.startswith("SELECT id FROM organizations WHERE"):
                return [{"id": i} for i in state["org_ids"]]
            if state["stop"]:
                raise _Stop
            return []

    class Db:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *_):
            return False

    async def yes():
        return True

    monkeypatch.setattr(manage, "database_exists", yes)
    monkeypatch.setattr(manage, "contacts_tables_exist", yes)
    for module in (database, report, lookup):
        monkeypatch.setattr(module, "get_db", Db)
    return sent


def test_the_rule_is_name_short_name_or_local_name():
    assert database.org_condition("organization_id", "$1") == ORG_RULE
    assert database.org_pattern("ADB") == "%ADB%"


async def test_contact_list_matches_the_short_name(sql):
    result = await manage.contacts([{"op": "contact_list", "organization": "ADB"}])

    assert result["summary"]["errors"] == 0
    query, params = sql[-1]
    assert ORG_RULE in query
    assert params == ("%ADB%",)


async def test_export_contacts_filters_by_the_same_rule(sql):
    sql.state["stop"] = True

    await manage.contacts([{"op": "export_contacts", "filter_params": {"organization": "ADB"}}])

    query, params = sql[0]
    assert "c." + ORG_RULE in query
    assert params == ("%ADB%",)


async def test_export_keeps_the_rule_after_a_project_filter(sql):
    sql.state["stop"] = True

    await manage.contacts([{"op": "export_contacts",
                            "filter_params": {"project_id": 15, "organization": "ADB"}}])

    query, params = sql[0]
    assert "cp.project_id = $1" in query
    assert "c." + ORG_RULE.replace("$1", "$2") in query
    assert params == (15, "%ADB%")


async def test_the_organization_report_uses_the_same_rule(sql):
    result = await manage.contacts([{"op": "report", "report_type": "organization",
                                     "organization": "ADB"}])

    assert result["summary"]["errors"] == 0
    query, params = sql[0]
    assert "c." + ORG_RULE in query
    assert params == ("%ADB%", 50)


def _two_andrews(monkeypatch):
    found = [{"id": 1, "match_score": 90}, {"id": 2, "match_score": 90}]
    people = {
        1: {"id": 1, "display_name": "Andrew A", "organization_id": 9,
            "organization_name": "Deutsche Gesellschaft für Internationale Zusammenarbeit GmbH",
            "channels": [], "projects": []},
        2: {"id": 2, "display_name": "Andrew B", "organization_id": 5,
            "organization_name": "Asian Development Bank", "channels": [], "projects": []},
    }

    async def search(identifier, limit=5, threshold=70):
        return found

    async def get(contact_id):
        return people[contact_id]

    monkeypatch.setattr(lookup, "contact_search", search)
    monkeypatch.setattr(lookup, "_get_contact_with_channels", get)


@pytest.mark.parametrize("op, extra", [
    ("contact_resolve", {"identifier": "Andrew"}),
    ("contact_resolve_multiple", {"identifiers": ["Andrew"]}),
])
async def test_resolve_prefers_the_contact_of_the_organization_in_context(sql, monkeypatch, op, extra):
    _two_andrews(monkeypatch)
    sql.state["org_ids"] = [5]

    result = await manage.contacts([{"op": op, **extra, "context": {"organization": "ADB"}}])

    answer = result["results"][0]["result"]
    resolved = answer if op == "contact_resolve" else answer["resolved"][0]["contact"]
    assert (resolved["id"], resolved["resolved_by"]) == (2, "name_with_org_context")
    assert sql[0] == ("SELECT id FROM organizations WHERE name ILIKE $1 "
                      "OR short_name ILIKE $1 OR name_local ILIKE $1", ("%ADB%",))


async def test_resolve_without_a_matching_organization_falls_back_to_the_best_name(sql, monkeypatch):
    _two_andrews(monkeypatch)
    sql.state["org_ids"] = []

    result = await manage.contacts([{"op": "contact_resolve", "identifier": "Andrew",
                                     "context": {"organization": "Nobody Inc"}}])

    resolved = result["results"][0]["result"]
    assert (resolved["id"], resolved["resolved_by"]) == (1, "name")


async def test_resolve_without_an_organization_hint_does_not_look_one_up(sql, monkeypatch):
    _two_andrews(monkeypatch)

    await manage.contacts([{"op": "contact_resolve", "identifier": "Andrew",
                            "context": {"role_name": "Team Leader"}}])

    assert sql == []


def test_the_docstring_states_the_rule():
    doc = manage.contacts.__doc__
    assert doc.count("name, short name or local name") >= 3  # list, resolve context, export
