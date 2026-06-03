"""Tests for DATE-column coercion in the database tool layer.

Reproduces the bug where ISO date strings were passed straight to asyncpg for
DATE columns, raising "'str' object has no attribute 'toordinal'". The fix
coerces incoming values to datetime.date before they reach a query. The helper
is shared by the projects and contacts handlers.
"""

from datetime import date, datetime

import pytest

from google_calendar.db.dates import coerce_date, coerce_date_fields, DATE_FIELDS


def test_plain_iso_string():
    assert coerce_date("2026-05-01") == date(2026, 5, 1)


def test_iso_string_with_time_component():
    # The reporter hit the bug with this form too.
    assert coerce_date("2026-05-01T00:00:00") == date(2026, 5, 1)


def test_none_passes_through():
    assert coerce_date(None) is None


def test_empty_string_becomes_none():
    assert coerce_date("  ") is None


def test_date_passes_through_unchanged():
    d = date(2026, 4, 30)
    assert coerce_date(d) is d


def test_datetime_is_narrowed_to_date():
    assert coerce_date(datetime(2026, 4, 30, 12, 34, 56)) == date(2026, 4, 30)


def test_coerced_value_has_toordinal():
    # asyncpg calls .toordinal() on DATE params; the coerced result must expose it.
    assert coerce_date("2026-05-01").toordinal() > 0


def test_invalid_type_raises():
    with pytest.raises(TypeError):
        coerce_date(12345)


def test_coerce_date_fields_in_place():
    updates = {
        "start_date": "2026-05-01",
        "end_date": "2026-04-30T00:00:00",
        "last_interaction_date": "2026-06-01",
        "description": "unchanged",
    }
    coerce_date_fields(updates)
    assert updates["start_date"] == date(2026, 5, 1)
    assert updates["end_date"] == date(2026, 4, 30)
    assert updates["last_interaction_date"] == date(2026, 6, 1)
    assert updates["description"] == "unchanged"


def test_coerce_date_fields_ignores_absent_keys():
    updates = {"description": "no dates here"}
    coerce_date_fields(updates)
    assert updates == {"description": "no dates here"}


def test_coerce_date_fields_preserves_explicit_null():
    # contact_update may set last_interaction_date back to NULL.
    updates = {"last_interaction_date": None}
    coerce_date_fields(updates)
    assert updates["last_interaction_date"] is None


def test_date_fields_constant_covers_all_schema_date_columns():
    # Guard against drift: the union of DATE columns written via the tool layer
    # across projects, organizations, project_organizations, contacts and
    # contact_projects.
    assert set(DATE_FIELDS) == {
        "start_date",
        "end_date",
        "first_contact_date",
        "last_interaction_date",
    }
