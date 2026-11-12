"""Per-operation parameter check for the batch tools (projects, contacts).

Each operation reads a fixed set of keys. A key it does not read used to be ignored
silently, so a mistyped or wrongly documented filter returned an unfiltered list that
looked filtered (issues #6, #7, #8). Every operation now refuses keys it does not read,
including the inner keys of its dict-valued parameters.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Iterable

# Accepted by every operation: the dispatcher's own key, and the account callers pass along.
COMMON_KEYS = frozenset({"op", "account"})


def check_keys(
    op: object,
    params: Mapping[str, object],
    op_keys: Mapping[str, Iterable[str]],
    notes: Mapping[str, str] | None = None,
    nested: Mapping[tuple[str, str], Iterable[str]] | None = None,
) -> None:
    """Raise ValueError unless `op` is known and every key (and inner key) is one it reads.

    An operation missing from `op_keys` never runs: the table is the list of operations.
    """
    if not isinstance(op, str) or op not in op_keys:
        raise ValueError(f"Unknown operation: {op}")

    keys = set(op_keys[op])
    unknown = sorted(set(params) - keys - COMMON_KEYS)
    if unknown:
        note = f" ({notes[op]})" if notes and op in notes else ""
        supported = ", ".join(sorted(keys)) or "none"
        raise ValueError(f"{op}: unknown parameter(s) {', '.join(unknown)}; supported: {supported}{note}")

    for (nested_op, param), inner_keys in (nested or {}).items():
        value = params.get(param) if nested_op == op else None
        if value is None:
            continue
        inner = ", ".join(sorted(inner_keys))
        if not isinstance(value, Mapping):
            raise ValueError(f"{op}: {param} must be an object with keys from: {inner}")
        bad = sorted(set(value) - set(inner_keys))
        if bad:
            raise ValueError(f"{op}: unknown {param} key(s) {', '.join(bad)}; supported: {inner}")
