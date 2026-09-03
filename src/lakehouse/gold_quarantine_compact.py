"""Gold quarantine compact / rewrite policy.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(Gold Hive ``quarantine/reason=/metric=/dt=`` keys vs a max-objects
threshold) and optionally folds in live S3 objects when MiniStack answers.

Repeated Gold runs can leave many small ``part-*.json`` files in one
quarantine partition. Compaction rewrites them into a single object and
drops the extras. ``python -m lakehouse gold-quarantine-compact`` prints
JSON. Default is dry-run (``apply=false``). Exit code 1 means compact was
requested and a rewrite or delete failed.

Max objects per partition comes from
``LAKEHOUSE_GOLD_QUARANTINE_COMPACT_MAX_OBJECTS`` (default 2) or
``--max-objects``.
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

DEFAULT_MAX_OBJECTS = 2
DATASET_ID = "gold.quarantine"
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
    raw = os.environ.get("LAKEHOUSE_GOLD_QUARANTINE_COMPACT_MAX_OBJECTS")
    if raw and raw.strip():
        return max(int(raw), 1)
    return DEFAULT_MAX_OBJECTS


def compact_key(*, reason: str, metric: str, dt: str) -> str:
    return f"{PREFIX}reason={reason}/metric={metric}/dt={dt}/{COMPACT_NAME}"


def classify_partition(
    *,
    reason: str,
    metric: str,
    dt: date | str,
    objects: int,
    max_objects: int,
    keys: list[str] | None = None,
) -> dict[str, Any]:
    """Mark one Gold quarantine partition as keep or compact."""

    parsed = date.fromisoformat(dt) if isinstance(dt, str) else dt
    count = int(objects)
    needs = count > int(max_objects)
    label_reason = reason or "unknown"
    label_metric = metric or "unknown"
    return {
        "dataset": DATASET_ID,
        "reason": label_reason,
        "metric": label_metric,
        "dt": parsed.isoformat(),
        "objects": count,
        "max_objects": int(max_objects),
        "keys": list(keys or []),
        "target": compact_key(
            reason=label_reason,
            metric=label_metric,
            dt=parsed.isoformat(),
        ),
        "action": "compact" if needs else "keep",
        "compact": needs,
    }


def plan_compact(
    partitions: list[dict[str, Any]],
    *,
    max_objects: int | None = None,
) -> dict[str, Any]:
    """Classify a list of ``{reason, metric, dt, objects, keys?}`` partitions."""

    budget = resolve_max_objects(max_objects)
    rows = [
        classify_partition(
            reason=str(item.get("reason") or "unknown"),
            metric=str(item.get("metric") or "unknown"),
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


def spec_snapshot(*, max_objects: int | None = None) -> dict[str, Any]:
    """Offline plan used by unit tests and when MiniStack is down."""

    today = date(2026, 9, 1)
    week = date(2026, 8, 25)
    budget = resolve_max_objects(max_objects)
    fixtures = [
        {
            "reason": "unreadable_silver",
            "metric": "purchase",
            "dt": today.isoformat(),
            "objects": 1,
            "keys": [
                compact_key(
                    reason="unreadable_silver",
                    metric="purchase",
                    dt=today.isoformat(),
                ),
            ],
        },
        {
            "reason": "unknown_event_type",
            "metric": "page_view",
            "dt": week.isoformat(),
            "objects": budget + 2,
            "keys": [
                (
                    f"quarantine/reason=unknown_event_type/metric=page_view/"
                    f"dt={week.isoformat()}/part-{i:03d}.json"
                )
                for i in range(budget + 2)
            ],
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
