"""
Shared OAuth state storage.

Stores pending OAuth flows that are waiting for callback from Google.
Separated to avoid circular imports between client.py and oauth_server.py.
"""

import time
import secrets
from typing import Optional

# In-memory state store for pending OAuth flows
_pending_flows: dict[str, dict] = {}

# Pending flow TTL: 15 minutes
PENDING_FLOW_TTL_SECONDS = 900

# Maximum pending flows to prevent memory issues
MAX_PENDING_FLOWS = 100


def cleanup_expired_flows() -> None:
    """Remove expired pending flows."""
    now = time.time()
    expired = [
        state for state, data in _pending_flows.items()
        if now - data.get("created_at", 0) > PENDING_FLOW_TTL_SECONDS
    ]
    for state in expired:
        _pending_flows.pop(state, None)


def generate_state() -> str:
    """Generate a secure random state token."""
    return secrets.token_urlsafe(32)


def store_pending_flow(state: str, account: str, flow, email_hint: Optional[str] = None) -> bool:
    """
    Store a pending OAuth flow.

    Returns True if stored, False if limit reached.
    """
    cleanup_expired_flows()

    if len(_pending_flows) >= MAX_PENDING_FLOWS:
        return False

    _pending_flows[state] = {
        "account": account,
        "flow": flow,
        "email_hint": email_hint,
        "created_at": time.time()
    }
    return True


def get_pending_flow(state: str) -> Optional[dict]:
    """Get and remove a pending flow by state token."""
    return _pending_flows.pop(state, None)


def get_pending_flow_data(state: str) -> Optional[dict]:
    """Get pending flow data without removing it."""
    return _pending_flows.get(state)
