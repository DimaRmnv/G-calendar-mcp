"""projects(org_get, name=...): a name finds the organization by its full, short or local name.

The docstring teaches `org_get(name="ADB")`, but the lookup compared the full name
only, case-sensitively, so "ADB" came back as null although "Asian Development Bank"
(short name ADB) exists. Now a name matches the whole full name, short name or local
name in any case. Several matches are refused with the candidates' ids, and a call
with neither id nor a name is refused instead of answering null.
The tests record the SQL sent to a stubbed connection.
"""
from __future__ import annotations

import pytest

import google_calendar.tools.projects.database as database
import google_calendar.tools.projects.manage as manage

BY_NAME = ("SELECT * FROM organizations WHERE lower(name) = lower($1) "
           "OR lower(short_name) = lower($1) OR lower(name_local) = lower($1) ORDER BY id")
BY_ID = "SELECT * FROM organizations WHERE id = $1"

ADB = {"id": 5, "name": "Asian Development Bank", "short_name": "ADB", "name_local": None}
ADF = {"id": 8, "name": "African Development Fund", "short_name": "ADB", "name_local": None}


@pytest.fixture
def db(monkeypatch):
    """Connection stub: records (query, params); organization lookups answer `rows`."""
    sent: list = []
    state = {"rows": []}

    class Conn:
        async def fetch(self, query, *params):
            sent.append((" ".join(query.split()), params))
            return list(state["rows"])

        async def fetchrow(self, query, *params):
            sent.append((" ".join(query.split()), params))
            return state["rows"][0] if state["rows"] else None

    class Db:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *_):
            return False

    async def yes():
        return True

    monkeypatch.setattr(manage, "database_exists", yes)
    monkeypatch.setattr(database, "get_db", Db)
    return sent, state


async def _org_get(**params):
    out = await manage.projects([{"op": "org_get", **params}])
    return out["results"][0]


async def test_the_short_name_finds_the_organization(db):
    sent, state = db
    state["rows"] = [ADB]

    result = await _org_get(name="ADB")

    assert result.get("error") is None, result
    assert result["result"]["id"] == 5
    assert sent == [(BY_NAME, ("ADB",))]


@pytest.mark.parametrize("name", ["asian development bank", "  ADB  "])
async def test_any_case_and_surrounding_spaces(db, name):
    sent, state = db
    state["rows"] = [ADB]

    result = await _org_get(name=name)

    assert result["result"]["id"] == 5
    assert sent == [(BY_NAME, (name.strip(),))]


async def test_several_matches_are_refused_with_their_ids(db):
    sent, state = db
    state["rows"] = [ADB, ADF]

    result = await _org_get(name="ADB")

    assert "result" not in result
    assert "5" in result["error"] and "8" in result["error"]
    assert "id" in result["error"]


async def test_no_match_is_null_as_before(db):
    sent, state = db

    result = await _org_get(name="Nobody")

    assert result.get("error") is None, result
    assert result["result"] is None


@pytest.mark.parametrize("params", [{}, {"name": ""}, {"name": "   "}])
async def test_neither_id_nor_a_name_is_refused_before_any_query(db, params):
    sent, state = db

    result = await _org_get(**params)

    assert "id or name" in result["error"]
    assert sent == []


async def test_the_id_lookup_is_unchanged(db):
    sent, state = db
    state["rows"] = [ADB]

    result = await _org_get(id=5)

    assert result["result"]["id"] == 5
    assert sent == [(BY_ID, (5,))]


@pytest.mark.parametrize("name", ["Other Org", 5, None, "  "])
async def test_an_id_wins_over_any_name(db, name):
    sent, state = db
    state["rows"] = [ADB]

    result = await _org_get(id=5, name=name)

    assert result["result"]["id"] == 5
    assert sent == [(BY_ID, (5,))]


async def test_a_name_that_is_not_text_is_refused_before_any_query(db):
    sent, state = db

    result = await _org_get(name=5)

    assert result["error"] == "org_get: name must be text"
    assert sent == []
