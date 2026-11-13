"""Time values sent to the Google Calendar API."""

from datetime import date, datetime, time, timedelta

from google_calendar.errors import InputError, zone


def has_offset(value: str) -> bool:
    """True for an ISO datetime that carries its own offset (or Z)."""
    return "T" in value and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None


def as_aware(value: str, timezone: str | None) -> datetime:
    """Parse an ISO datetime; a value without an offset is local time in `timezone`."""
    if "T" not in value:
        raise ValueError(f"Expected datetime, got date: {value}")

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed
    if not timezone:
        raise ValueError(f"No timezone to interpret the local time {value}")
    return parsed.replace(tzinfo=zone(timezone))


def to_rfc3339(value: str, timezone: str | None) -> str:
    """RFC3339 timestamp for a time-range parameter (timeMin, timeMax, freebusy bounds).

    A value with an offset (or Z) keeps it. A naive value is local time in `timezone`
    (owner decision 2026-11-12, issue #3) — it used to be read as UTC.
    """
    return as_aware(value, timezone).isoformat()


def check_bounds(*values: str | None) -> None:
    """Refuse a malformed time-window bound before anything is asked of Google.

    A bound is a date ('2026-11-09') or an ISO datetime; None or '' means "not given".
    """
    for value in values:
        if not value:
            continue
        try:
            if "T" in value:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                date.fromisoformat(value)
        except ValueError as exc:
            raise InputError(
                f"Invalid time bound {value!r}: expected a date ('2026-11-09') "
                "or an ISO datetime ('2026-11-09T10:00:00')"
            ) from exc


def window_point(value: str, timezone: str | None, *, end: bool) -> datetime:
    """One bound of a time window (timeMin or timeMax) as an aware datetime.

    A date ('2026-11-09') is that whole day on the clock of `timezone`: as the start
    bound it is the day's midnight, as the end bound the next midnight — Google's
    timeMax is exclusive, so the last moment of the day is still inside. A datetime
    follows as_aware. A local value (a date, or a datetime without an offset) carries
    the zone itself, not a fixed offset, so a span added to it (the 7-day window, the
    search year) is counted on the local clock across a DST change; a value with its
    own offset keeps that offset. One rule for every window a tool takes (issue #9).
    """
    check_bounds(value)
    if "T" in value:
        return as_aware(value, timezone)
    if not timezone:
        raise ValueError(f"No timezone to interpret the date {value}")
    day = date.fromisoformat(value)
    if end:
        day += timedelta(days=1)
    return datetime.combine(day, time(), zone(timezone))


def window_bound(value: str, timezone: str | None, *, end: bool) -> str:
    """window_point as an RFC3339 timestamp."""
    return window_point(value, timezone, end=end).isoformat()
