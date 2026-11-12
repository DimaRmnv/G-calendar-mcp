"""projects(project_list / org_list): the filters the docstring teaches are the ones the code reads.

Issue #6. The docstring told the model to filter with `is_active` / `is_billable`, while
the handlers read `active_only` / `billable_only`, so the filter was silently dropped and
an unfiltered list came back as if it were filtered. Now the docstring names the real
filters, and an unknown filter key is refused instead of ignored.
"""
from __future__ import annotations

import inspect

import pytest

import google_calendar.tools.projects.manage as manage


@pytest.fixture
def db(monkeypatch):
    """Database layer stubbed at the names manage.py uses; records the filters received."""
    received = {}

    async def exists():
        return True

    async def project_list(**filters):
        received["project_list"] = filters
        return []

    async def org_list(**filters):
        received["org_list"] = filters
        return []

    monkeypatch.setattr(manage, "database_exists", exists)
    monkeypatch.setattr(manage, "project_list", project_list)
    monkeypatch.setattr(manage, "org_list", org_list)
    return received


async def test_project_list_filters_reach_the_query(db):
    result = await manage.projects([{"op": "project_list", "active_only": True, "billable_only": True}])

    assert result["summary"]["errors"] == 0
    assert db["project_list"] == {"active_only": True, "billable_only": True}


async def test_org_list_filters_reach_the_query(db):
    await manage.projects([{"op": "org_list", "organization_type": "donor", "country": "KG",
                            "relationship_status": "active", "active_only": False}])

    assert db["org_list"] == {"organization_type": "donor", "country": "KG",
                              "relationship_status": "active", "active_only": False}


@pytest.mark.parametrize("op, wrong, right", [
    ("project_list", "is_active", "active_only"),
    ("project_list", "is_billable", "billable_only"),
    ("org_list", "is_active", "active_only"),
])
async def test_an_unknown_filter_is_refused_not_ignored(db, op, wrong, right):
    result = await manage.projects([{"op": op, wrong: True}])

    error = result["results"][0]["error"]
    assert wrong in error and right in error
    assert op not in db  # the query never ran with the filter dropped


async def test_an_account_passed_along_is_not_an_error(db):
    result = await manage.projects([{"op": "project_list", "account": "work", "active_only": True}])

    assert result["summary"]["errors"] == 0
    assert db["project_list"] == {"active_only": True, "billable_only": False}


def test_the_docstring_teaches_the_filters_the_code_reads():
    doc = inspect.getdoc(manage.projects)

    assert "project_list        : All projects (compact). Filters: active_only, billable_only\n" in doc
    assert "relationship_status, active_only (default true)." in doc
    assert '"project_list", "is_active"' not in doc
    assert '{"op": "project_list", "active_only": true}' in doc
