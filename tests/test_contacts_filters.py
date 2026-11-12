"""contacts(contact_list): the filters the docstring teaches are the ones the code reads.

Issue #7 (the sibling of #6). The docstring taught `organization_id`, while the handler
reads `organization` (a name, partial match), so the filter was silently dropped and the
list came back unfiltered by organization as if it had been filtered. The docstring now
names the real filters, and an unknown filter key is refused instead of ignored.
"""
from __future__ import annotations

import inspect

import pytest

import google_calendar.tools.contacts.manage as manage

ALL_FILTERS = {"organization": "ADB", "country": "KG", "project_id": 5, "role_name": "Team Leader",
               "preferred_channel": "email", "org_type": "donor", "active_only": False}


@pytest.fixture
def db(monkeypatch):
    """Database layer stubbed at the names manage.py uses; records the filters received."""
    received = {}

    async def yes():
        return True

    async def contact_list(**filters):
        received["contact_list"] = filters
        return []

    monkeypatch.setattr(manage, "database_exists", yes)
    monkeypatch.setattr(manage, "contacts_tables_exist", yes)
    monkeypatch.setattr(manage, "contact_list", contact_list)
    return received


async def test_every_contact_list_filter_reaches_the_query(db):
    result = await manage.contacts([{"op": "contact_list", **ALL_FILTERS}])

    assert result["summary"]["errors"] == 0
    assert db["contact_list"] == ALL_FILTERS


@pytest.mark.parametrize("wrong", ["organization_id", "is_active", "org"])
async def test_an_unknown_filter_is_refused_not_ignored(db, wrong):
    result = await manage.contacts([{"op": "contact_list", wrong: 5}])

    error = result["results"][0]["error"]
    assert wrong in error and "organization" in error and "preferred_channel" in error
    assert "contact_list" not in db  # the query never ran with the filter dropped


async def test_an_account_passed_along_is_not_an_error(db):
    result = await manage.contacts([{"op": "contact_list", "account": "work", "country": "KG"}])

    assert result["summary"]["errors"] == 0
    assert db["contact_list"]["country"] == "KG"


def test_the_docstring_teaches_the_filters_the_code_reads():
    doc = inspect.getdoc(manage.contacts)
    line = next(ln for ln in doc.splitlines() if ln.strip().startswith("contact_list    :"))
    block = line + doc.split(line, 1)[1].split("contact_search", 1)[0]

    assert "organization_id" not in block
    for name in ALL_FILTERS:
        assert name in block, name
