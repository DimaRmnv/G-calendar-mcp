"""Per-operation parameter check for the batch tools (projects, contacts).

Each operation reads a fixed set of keys. A key it does not read used to be ignored
silently, so a mistyped or wrongly documented filter returned an unfiltered list that
looked filtered (issues #6, #7, #8). Every operation now refuses keys it does not read.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Iterable

# Accepted by every operation: the dispatcher's own key, and the account callers pass along.
COMMON_KEYS = frozenset({"op", "account"})


def check_keys(
    op: str,
    params: Mapping[str, object],
    op_keys: Mapping[str, Iterable[str]],
    notes: Mapping[str, str] | None = None,
) -> None:
    """Raise ValueError naming every key `op` does not read (unknown ops are left to the dispatcher)."""
    keys = op_keys.get(op)
    if keys is None:
        return
    unknown = sorted(set(params) - set(keys) - COMMON_KEYS)
    if unknown:
        note = f" ({notes[op]})" if notes and op in notes else ""
        supported = ", ".join(sorted(keys)) or "none"
        raise ValueError(f"{op}: unknown parameter(s) {', '.join(unknown)}; supported: {supported}{note}")
