"""Keep credentials that ride in a request URL out of the server log.

The API key is accepted as `?api_key=` and as a `/key/{key}/` path segment, the
Google start link carries a signed `?token=`, and the Google callback carries
the authorization `code` and `state`. uvicorn logs the path and the whole query
string of every request, so `serve()` gives uvicorn a logging configuration whose
handlers pass each record through `RedactSecretsFilter` first.

Everything here is a single linear pass (split / partition / unquote): the filter
runs on every request inside the event loop, so a backtracking pattern would let one
long URL stall the server.
"""
from __future__ import annotations

import copy
import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, unquote, unquote_plus

REDACTED = "REDACTED"

# Query parameters whose value is a credential. Matched on the decoded, lower-cased
# name: Starlette decodes names (`api%5Fkey` reads as `api_key`), so the log must too.
SECRET_PARAMS = frozenset({
    "api_key", "token", "code", "state",
    "access_token", "refresh_token", "client_secret", "secret",
})

# Starlette's request.url (which the auth middleware reads the /key/ segment from) is
# built with urlsplit, and urlsplit deletes these characters wherever they are.
_URLSPLIT_DROPS = str.maketrans("", "", "\t\r\n")

# Free text is cut into tokens at whitespace and quotes before tokens are redacted.
_TOKEN_BREAK = re.compile(r'(\s+|["\'])')


def _redact_query(query: str) -> str:
    """Replace the value of every credential parameter; `&` and `;` both separate.

    `;` is no separator for Starlette, and a name led by `?` is not the parameter it
    spells, so such a key is refused by the server; it is still a real key, so it is
    redacted all the same.
    """
    pieces = re.split(r"([&;])", query)
    for i in range(0, len(pieces), 2):
        name, eq, _ = pieces[i].partition("=")
        if eq and unquote_plus(name).translate(_URLSPLIT_DROPS).lstrip("?").lower() in SECRET_PARAMS:
            pieces[i] = f"{name}={REDACTED}"
    return "".join(pieces)


def _redact_path(path: str) -> str:
    """Replace the segment after every `/key/`, as the auth middleware would read it.

    The middleware reads the decoded path with tab, CR and LF removed (urlsplit), so
    `/k%09ey/<key>/` is a key too. The path is rewritten from that reading only when it
    holds `/key/`; otherwise it is returned as logged.
    """
    view = unquote(path).translate(_URLSPLIT_DROPS)
    if "/key/" not in view:
        return path
    head, *chunks = view.split("/key/")
    out = [quote(head)]
    for chunk in chunks:
        _, slash, rest = chunk.partition("/")
        out.append(f"/key/{REDACTED}{slash}{quote(rest)}")
    return "".join(out)


def redact_url(url: str) -> str:
    """A path with an optional query string, with its credentials replaced by REDACTED."""
    path, mark, query = url.partition("?")
    return _redact_path(path) + mark + (_redact_query(query) if mark else "")


def redact_text(text: str) -> str:
    """Free text with every URL-like token passed through redact_url."""
    parts = _TOKEN_BREAK.split(text)
    for i in range(0, len(parts), 2):
        if "?" in parts[i] or "/" in parts[i]:
            parts[i] = redact_url(parts[i])
    return "".join(parts)


class RedactSecretsFilter(logging.Filter):
    """Redact URL credentials in every record a handler emits.

    uvicorn's access record keeps its five arguments (client, method, path with query,
    HTTP version, status) because its formatter unpacks them; only the path is
    rewritten. In any other record each text argument is read whole as a URL (uvicorn's
    WebSocket lines pass the path with its query as one), then the formatted text is
    redacted again token by token for URLs written into the template itself. Such a
    record is rewritten only when redaction changed something.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if (record.name == "uvicorn.access" and isinstance(args, tuple) and len(args) == 5
                and isinstance(args[2], str)):
            record.args = (*args[:2], redact_url(args[2]), *args[3:])
            return True
        if isinstance(args, tuple):
            safe_args: Any = tuple(redact_url(a) if isinstance(a, str) else a for a in args)
        elif isinstance(args, Mapping):
            safe_args = {k: redact_url(v) if isinstance(v, str) else v for k, v in args.items()}
        else:
            safe_args = args
        broken = False
        try:
            original = record.getMessage()
            message = str(record.msg) % safe_args if args else original
        except (TypeError, ValueError, KeyError):
            # A log call whose arguments do not fit its template: logging would print the
            # raw arguments to stderr, so keep the template and drop them.
            original = message = f"{record.msg} [log arguments dropped: they did not fit the message]"
            broken = True
        redacted = redact_text(message)
        if broken or redacted != original:
            record.msg = redacted
            record.args = ()
            # uvicorn's coloured formatter would re-apply the original arguments to this.
            record.__dict__.pop("color_message", None)
        return True


def uvicorn_log_config() -> dict[str, Any]:
    """The server's logging configuration: uvicorn's default plus the app's own logger.

    Without a handler of its own the `google_calendar` logger reached the container
    log only at WARNING and above (Python's last-resort handler), so INFO lines such as
    the export cleanup and input-error reasons were lost. Every handler, the app's
    included, passes records through the redaction filter.
    """
    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    config.setdefault("filters", {})["redact_secrets"] = {
        "()": "google_calendar.log_redaction.RedactSecretsFilter",
    }
    config["formatters"]["app"] = {
        "()": "uvicorn.logging.DefaultFormatter",
        "fmt": "%(levelprefix)s %(name)s: %(message)s",
        "use_colors": None,
    }
    config["handlers"]["app"] = {
        "formatter": "app",
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stderr",
    }
    config["loggers"]["google_calendar"] = {
        "handlers": ["app"], "level": "INFO", "propagate": False,
    }
    for handler in config["handlers"].values():
        handler.setdefault("filters", []).append("redact_secrets")
    return config
