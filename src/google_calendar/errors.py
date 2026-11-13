"""Errors a tool answers with when the caller has to change the request."""

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)


class InputError(ToolError, ValueError):
    """A missing or malformed parameter, an unknown action, timezone or account.

    fastmcp logs a plain exception from a tool at ERROR with the traceback and prefixes
    the answer with "Error calling tool ...". A ToolError is logged at its own level as
    one line and its message reaches the client as written. Input errors are logged at
    INFO: the server did not fail. Still a ValueError, so code that collects ValueErrors
    per operation (projects, contacts, events batch) keeps collecting them.
    """

    def __init__(self, message: str):
        super().__init__(message, log_level=logging.INFO)
        # fastmcp's own line names only the tool. The reason is logged here, as a repr so
        # that a caller's value with a line break cannot forge a log line.
        logger.info("Input error: %r", message)


def zone(name: str) -> ZoneInfo:
    """The IANA timezone `name`; an unknown name is the caller's error."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InputError(
            f"Unknown timezone {name!r}: expected an IANA name such as 'Europe/London'"
        ) from exc
