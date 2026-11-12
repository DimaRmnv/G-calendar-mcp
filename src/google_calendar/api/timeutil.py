"""Time values sent to the Google Calendar API."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


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
    return parsed.replace(tzinfo=ZoneInfo(timezone))


def to_rfc3339(value: str, timezone: str | None) -> str:
    """RFC3339 timestamp for a time-range parameter (timeMin, timeMax, freebusy bounds).

    A value with an offset (or Z) keeps it. A naive value is local time in `timezone`
    (owner decision 2026-11-12, issue #3) — it used to be read as UTC.
    """
    return as_aware(value, timezone).isoformat()


def window_bound(value: str, timezone: str | None, *, end: bool) -> str:
    """One bound of a time window (timeMin or timeMax) as an RFC3339 timestamp.

    A date ('2026-11-09') is that whole day on the clock of `timezone`: as the start
    bound it is the day's midnight, as the end bound the next midnight — Google's
    timeMax is exclusive, so the last moment of the day is still inside. A datetime
    follows to_rfc3339. One rule for every window a tool takes (issue #9).
    """
    if "T" in value:
        return to_rfc3339(value, timezone)
    day = date.fromisoformat(value)  # a malformed date is refused here
    if not timezone:
        raise ValueError(f"No timezone to interpret the date {value}")
    if end:
        day += timedelta(days=1)
    # combine() puts midnight on the local clock, so a DST change inside the window
    # still lands on the next local midnight.
    return datetime.combine(day, time(), ZoneInfo(timezone)).isoformat()
