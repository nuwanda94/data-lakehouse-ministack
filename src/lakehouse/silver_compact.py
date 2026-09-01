"""Silver cleaned-event compact / rewrite policy.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(Silver Hive ``events/event_type=/dt=`` keys vs a max-objects threshold)
and optionally folds in live S3 objects when MiniStack answers.

Silver writes one JSON object per cleaned event. Compaction rewrites a
fragmented ``event_type`` + day prefix into a single ``part-000.json``
and drops the siblings. ``python -m lakehouse silver-compact`` prints
JSON. Default is dry-run (``apply=false``). Exit code 1 means compact
was requested and a rewrite or delete failed.

Max objects per partition comes from
``LAKEHOUSE_SILVER_COMPACT_MAX_OBJECTS`` (default 8) or ``--max-objects``.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings
from lakehouse.partitions import parse_hive_key

DEFAULT_MAX_OBJECTS = 8
DATASET_ID = "silver.cleaned_events"
PREFIX = "events/"
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
    raw = os.environ.get("LAKEHOUSE_SILVER_COMPACT_MAX_OBJECTS")
    if raw and raw.strip():
        return max(int(raw), 1)
    return DEFAULT_MAX_OBJECTS


def compact_key(*, event_type: str, dt: str) -> str:
    return f"{PREFIX}event_type={event_type}/dt={dt}/{COMPACT_NAME}"


def classify_partition(
    *,
    event_type: str,
    dt: date | str,
    objects: int,
    max_objects: int,
    keys: list[str] | None = None,
) -> dict[str, Any]:
    """Mark one Silver ``event_type=/dt=`` partition as keep or compact."""

    parsed = date.fromisoformat(dt) if isinstance(dt, str) else dt
    count = int(objects)
    needs = count > int(max_objects)
    return {
        "dataset": DATASET_ID,
        "event_type": event_type,
        "dt": parsed.isoformat(),
        "objects": count,
        "max_objects": int(max_objects),
        "keys": list(keys or []),
        "target": compact_key(event_type=event_type, dt=parsed.isoformat()),
        "action": "compact" if needs else "keep",
        "compact": needs,
    }


def plan_compact(
    partitions: list[dict[str, Any]],
    *,
    max_objects: int | None = None,
) -> dict[str, Any]:
    """Classify a list of ``{event_type, dt, objects, keys?}`` partitions."""

    budget = resolve_max_objects(max_objects)
    rows = [
        classify_partition(
            event_type=str(item.get("event_type") or "unknown"),
            dt=str(item.get("dt") or ""),
            objects=int(item.get("objects") or 0),
            max_objects=budget,
            keys=list(item.get("keys") or []),
        )
        for item in partitions
        if item.get("dt")
    ]
    compact = [row for row in rows if row["compact"]]
    keep = [row for row in rows if not row["compact"]]
    return {
        "dataset": DATASET_ID,
        "max_objects": budget,
        "partitions": rows,
        "keep_count": len(keep),
        "compact_count": len(compact),
        "compact": compact,
        "ok": True,
    }
