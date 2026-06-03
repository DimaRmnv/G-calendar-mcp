"""Tests for DATE-column coercion in the projects database layer.

Reproduces the bug where ISO date strings were passed straight to asyncpg for
DATE columns, raising "'str' object has no attribute 'toordinal'". The fix
coerces incoming values to datetime.date before they reach a query.
"""

from datetime import date, datetime

import pytest

from google_calendar.tools.projects.database import (
    _coerce_date,
    _coerce_date_fields,
    DATE_FIELDS,
)


def test_plain_iso_string():
    assert _coerce_date("2026-05-01") == date(2026, 5, 1)


def test_iso_string_with_time_component():
    # The reporter hit the bug with this form too.
    assert _coerce_date("2026-05-01T00:00:00") == date(2026, 5, 1)


def test_none_passes_through():
    assert _coerce_date(None) is None


def test_empty_string_becomes_none():
    assert _coerce_date("  ") is None


def test_date_passes_through_unchanged():
    d = date(2026, 4, 30)
    assert _coerce_date(d) is d


def test_datetime_is_narrowed_to_date():
    assert _coerce_date(datetime(2026, 4, 30, 12, 34, 56)) == date(2026, 4, 30)


def test_coerced_value_has_toordinal():
    # asyncpg calls .toordinal() on DATE params; the coerced result must expose it.
    assert _coerce_date("2026-05-01").toordinal() > 0


def test_invalid_type_raises():
    with pytest.raises(TypeError):
        _coerce_date(12345)


def test_coerce_date_fields_in_place():
    updates = {
        "start_date": "2026-05-01",
        "end_date": "2026-04-30T00:00:00",
        "description": "unchanged",
    }
    _coerce_date_fields(updates)
    assert updates["start_date"] == date(2026, 5, 1)
    assert updates["end_date"] == date(2026, 4, 30)
    assert updates["description"] == "unchanged"


def test_coerce_date_fields_ignores_absent_keys():
    updates = {"description": "no dates here"}
    _coerce_date_fields(updates)
    assert updates == {"description": "no dates here"}


def test_date_fields_constant_matches_schema():
    # Guard against drift: these are the DATE columns the projects layer writes.
    assert set(DATE_FIELDS) == {"start_date", "end_date", "first_contact_date"}
