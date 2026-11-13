"""Keep credentials that ride in a request URL out of the server log.

The API key is accepted as `?api_key=` and as a `/key/{key}/` path segment, the
Google start link carries a signed `?token=`, and the Google callback carries
the authorization `code` and `state`. uvicorn logs the path and the whole query
string of every request, so `serve()` gives uvicorn a logging configuration whose
handlers pass each record through `RedactSecretsFilter` first.
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any
from urllib.parse import unquote_plus

REDACTED = "REDACTED"

# Query parameters whose value is a credential. Matched on the decoded, lower-cased
# name: Starlette decodes names (`api%5Fkey` reads as `api_key`), so the log must too.
SECRET_PARAMS = frozenset({
    "api_key", "token", "code", "state",
    "access_token", "refresh_token", "client_secret", "secret",
})

_QUERY_PAIR = re.compile(r'([?&])([^=&#\s"]+)=([^&#\s"]*)')
# The auth middleware reads the key from the segment after any `/key/`.
_KEY_SEGMENT = re.compile(r'/key/[^/?#\s"]+')


def _redact_pair(match: re.Match) -> str:
    sep, name, value = match.groups()
    if unquote_plus(name).lower() in SECRET_PARAMS:
        return f"{sep}{name}={REDACTED}"
    return match.group(0)


def redact(text: str) -> str:
    """Return `text` with URL credentials replaced by REDACTED."""
    text = _KEY_SEGMENT.sub(f"/key/{REDACTED}", text)
    return _QUERY_PAIR.sub(_redact_pair, text)


class RedactSecretsFilter(logging.Filter):
    """Redact URL credentials in a record's arguments and message.

    uvicorn's access formatter unpacks the five arguments of the access record
    (client, method, path with query, HTTP version, status), so the arguments keep
    their shape and only string ones are rewritten.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


def uvicorn_log_config() -> dict[str, Any]:
    """uvicorn's default logging configuration with the redaction filter on every handler."""
    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    config.setdefault("filters", {})["redact_secrets"] = {
        "()": "google_calendar.log_redaction.RedactSecretsFilter",
    }
    for handler in config["handlers"].values():
        handler.setdefault("filters", []).append("redact_secrets")
    return config
