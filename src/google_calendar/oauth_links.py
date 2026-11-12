"""Signed, short-lived links that start the Google OAuth flow for one account.

The start route is public: a re-authorization link is opened from the chat in a
browser that has no API key. Without a signature anyone could start a flow for an
account and bind their own Google token to it. Only the server mints links (keyed
by the API key, so a key rotation voids them), each for one account, valid an hour.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import time

from google_calendar.settings import settings

LINK_TTL_SECONDS = 3600


def _key() -> bytes | None:
    if not settings.api_key:
        return None
    return hashlib.sha256(b"gcal-oauth-start-link:" + settings.api_key.encode()).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint(account: str, now: float | None = None) -> str | None:
    """Token for `?token=` of /oauth/start/{account}; None when no API key is set."""
    key = _key()
    if key is None:
        return None
    expires = int((time.time() if now is None else now) + LINK_TTL_SECONDS)
    payload = f"{account}:{expires}".encode()
    return f"{_b64(payload)}.{_b64(hmac.new(key, payload, hashlib.sha256).digest())}"


def verify(token: str | None, account: str, now: float | None = None) -> bool:
    """True only for an unexpired token this server minted for exactly `account`."""
    key = _key()
    if key is None or not token or token.count(".") != 1:
        return False
    payload_b64, sig_b64 = token.split(".")
    try:
        payload, sig = _unb64(payload_b64), _unb64(sig_b64)
        linked_account, _, expires = payload.decode().rpartition(":")
    except (binascii.Error, ValueError):
        return False
    if not hmac.compare_digest(sig, hmac.new(key, payload, hashlib.sha256).digest()):
        return False
    current = time.time() if now is None else now
    return linked_account == account and expires.isdigit() and int(expires) >= current


def start_is_open() -> bool:
    """A server with no authentication at all (local development) needs no link token."""
    return not settings.api_key and not (settings.oauth_client_id and settings.oauth_client_secret)
