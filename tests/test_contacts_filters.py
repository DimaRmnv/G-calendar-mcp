"""contacts(contact_list): every filter the docstring teaches reaches the SQL, or is refused.

Issue #7 (the sibling of #6). The docstring taught `organization_id`, while the handler
reads `organization` (a name, partial match), so the filter was silently dropped. The
verifier then showed two more silent drops: `active_only` (the views list active
contacts only) and the filters ignored by the project-team query. Now the docstring
names exactly what the SQL honours, and anything else is refused before any query runs.
The tests record the SQL actually sent, so a filter dropped below the handler shows.
"""
from __future__ import annotations

import inspect

import pytest

import google_calendar.tools.contacts.database as database
import google_calendar.tools.contacts.manage as manage


@pytest.fixture
def sql(monkeypatch):
    """Database stubbed at the connection; returns the list of (query, params) sent."""
    sent = []

    class Conn:
        async def fetch(self, query, *params):
            sent.append((" ".join(query.split()), params))
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
    monkeypatch.setattr(database, "get_db", Db)
    return sent


async def test_each_contact_filter_becomes_a_condition(sql):
    result = await manage.contacts([{"op": "contact_list", "organization": "ADB", "country": "KG",
                                     "org_type": "donor", "preferred_channel": "email"}])

    assert result["summary"]["errors"] == 0
    query, params = sql[-1]
    # `organization` follows the shared rule (name, short name or local name: issue #9,
    # tests/test_organization_match.py).
    for condition in ("organization_id IN (SELECT id FROM organizations WHERE name ILIKE $1",
                      "org_type =", "country =", "preferred_channel ="):
        assert condition in query, condition
    assert params == ("%ADB%", "donor", "KG", "email")


async def test_project_id_and_role_name_select_that_projects_team(sql):
    await manage.contacts([{"op": "contact_list", "project_id": 5, "role_name": "Team Leader"}])

    query, params = sql[-1]
    assert "FROM v_project_team WHERE project_id = $1 AND project_role ILIKE $2" in query
    assert params == (5, "%Team Leader%")


SUPPORTED = ("supported: country, org_type, organization, preferred_channel, project_id, role_name "
             "(only active contacts are listed)")


@pytest.mark.parametrize("filters, error", [
    # never existed / the views list active contacts only
    *[({key: False}, f"contact_list: unknown parameter(s) {key}; {SUPPORTED}")
      for key in ("organization_id", "is_active", "active_only")],
    # a role filters a project's team
    ({"role_name": "Team Leader"}, "contact_list: role_name filters a project's team; pass project_id too"),
    # the team query honours nothing else
    *[({"project_id": 5, key: "x"},
       f"contact_list: project_id lists that project's team and cannot be combined with {key}")
      for key in ("organization", "country", "org_type", "preferred_channel")],
])
async def test_a_filter_the_sql_cannot_honour_is_refused(sql, filters, error):
    result = await manage.contacts([{"op": "contact_list", **filters}])

    assert result["results"][0]["error"] == error
    assert sql == []  # no query ran with a filter dropped


async def test_an_account_passed_along_is_not_an_error(sql):
    result = await manage.contacts([{"op": "contact_list", "account": "work", "country": "KG"}])

    assert result["summary"]["errors"] == 0
    assert sql[-1][1] == ("KG",)


def test_the_docstring_teaches_exactly_the_filters_the_sql_honours():
    doc = inspect.getdoc(manage.contacts)
    line = next(ln for ln in doc.splitlines() if ln.strip().startswith("contact_list    :"))
    block = line + doc.split(line, 1)[1].split("contact_search", 1)[0]

    for name in ("organization", "country", "org_type", "preferred_channel", "project_id", "role_name"):
        assert name in block, name
    assert "organization_id" not in block
    assert "active_only" not in block
