"""Helpers for binding DATE-typed values to asyncpg queries.

asyncpg binds a DATE parameter by calling ``.toordinal()`` on it, so a bare ISO
string raises ``"'str' object has no attribute 'toordinal'"`` and the write
fails. MCP tool arguments arrive as JSON strings, so any value destined for a
DATE column must be coerced to ``datetime.date`` before it reaches a query.
"""

from datetime import date, datetime

# Every DATE-typed column written through the tool layer, across all tables
# (projects, organizations, project_organizations, contacts, contact_projects).
# coerce_date_fields() only touches keys actually present in the update dict, so
# carrying the full union here is safe for any caller.
DATE_FIELDS = ("start_date", "end_date", "first_contact_date", "last_interaction_date")


def coerce_date(value):
    """Coerce an incoming value to ``datetime.date`` for an asyncpg DATE column.

    Accepts ``None``, ``datetime.date``/``datetime.datetime`` or an ISO string in
    either ``'2026-05-01'`` or ``'2026-05-01T00:00:00'`` form. Empty/whitespace
    strings become ``None``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            # Fall back for values carrying a time component (e.g. '...T00:00:00').
            return datetime.fromisoformat(s).date()
    raise TypeError(f"Unsupported value for DATE column: {value!r}")


def coerce_date_fields(updates: dict, fields=DATE_FIELDS) -> None:
    """Coerce any DATE-typed keys of an update dict in place."""
    for key in fields:
        if key in updates:
            updates[key] = coerce_date(updates[key])
