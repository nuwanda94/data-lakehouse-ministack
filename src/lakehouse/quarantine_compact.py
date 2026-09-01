"""Silver quarantine compact / rewrite policy.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(quarantine ``reason=`` prefixes vs a max-objects threshold) and optionally
folds in live Silver ``quarantine/`` objects when MiniStack answers.

Quality-gate rejects land as one JSON object per event. Compaction
rewrites a fragmented ``reason=`` prefix into a single ``part-000.json``
and drops the siblings. ``python -m lakehouse quarantine-compact`` prints
JSON. Default is dry-run (``apply=false``). Exit code 1 means compact
was requested and a rewrite or delete failed.

Max objects per reason prefix comes from
``LAKEHOUSE_QUARANTINE_COMPACT_MAX_OBJECTS`` (default 8) or ``--max-objects``.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings
from lakehouse.quarantine_retention import parse_quarantine_key

DEFAULT_MAX_OBJECTS = 8
DATASET_ID = "silver.quarantine"
PREFIX = "quarantine/"
COMPACT_NAME = "part-000.json"


def _endpoint_reachable(url: str | None, timeout: float = 0.4) -> bool:
    """Cheap TCP probe so unit tests do not block on a down MiniStack."""

    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def resolve_max_objects(explicit: int | None = None) -> int:
    if explicit is not None:
        return max(int(explicit), 1)
    raw = os.environ.get("LAKEHOUSE_QUARANTINE_COMPACT_MAX_OBJECTS")
    if raw and raw.strip():
        return max(int(raw), 1)
    return DEFAULT_MAX_OBJECTS


def compact_key(*, reason: str) -> str:
    return f"{PREFIX}reason={reason}/{COMPACT_NAME}"


def classify_prefix(
    *,
    reason: str,
    objects: int,
    max_objects: int,
    keys: list[str] | None = None,
) -> dict[str, Any]:
    """Mark one quarantine ``reason=`` prefix as keep or compact."""

    count = int(objects)
    needs = count > int(max_objects)
    label = reason or "unknown"
    return {
        "dataset": DATASET_ID,
        "reason": label,
        "objects": count,
        "max_objects": int(max_objects),
        "keys": list(keys or []),
        "target": compact_key(reason=label),
        "action": "compact" if needs else "keep",
        "compact": needs,
    }


def plan_compact(
    prefixes: list[dict[str, Any]],
    *,
    max_objects: int | None = None,
) -> dict[str, Any]:
    """Classify a list of ``{reason, objects, keys?}`` prefixes."""

    budget = resolve_max_objects(max_objects)
    rows = [
        classify_prefix(
            reason=str(item.get("reason") or "unknown"),
            objects=int(item.get("objects") or 0),
            max_objects=budget,
            keys=list(item.get("keys") or []),
        )
        for item in prefixes
    ]
    compact = [row for row in rows if row["compact"]]
    keep = [row for row in rows if not row["compact"]]
    return {
        "dataset": DATASET_ID,
        "max_objects": budget,
        "prefixes": rows,
        "keep_count": len(keep),
        "compact_count": len(compact),
        "compact": compact,
        "ok": True,
    }


def spec_snapshot(*, max_objects: int | None = None) -> dict[str, Any]:
    """Offline plan used by unit tests and when MiniStack is down."""

    budget = resolve_max_objects(max_objects)
    fixtures = [
        {
            "reason": "schema",
            "objects": 1,
            "keys": ["quarantine/reason=schema/evt-keep-1.json"],
        },
        {
            "reason": "poison",
            "objects": budget + 2,
            "keys": [f"quarantine/reason=poison/evt-{i:03d}.json" for i in range(budget + 2)],
        },
    ]
    plan = plan_compact(fixtures, max_objects=budget)
    return {
        "backend": "spec",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": False,
        "rewritten": [],
        "deleted": [],
        **plan,
    }
