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
            "keys": [
                f"quarantine/reason=poison/evt-{i:03d}.json" for i in range(budget + 2)
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


def _live_quarantine_prefixes(settings: Settings) -> list[dict[str, Any]]:
    try:
        from lakehouse.aws import client
        from lakehouse.storage import list_keys

        s3 = client("s3", settings)
        keys = list_keys(s3, settings.silver_bucket, PREFIX)
        buckets: dict[str, dict[str, Any]] = {}
        for key in keys:
            reason = parse_quarantine_key(key).get("reason") or "unknown"
            row = buckets.setdefault(
                str(reason),
                {"reason": str(reason), "objects": 0, "keys": []},
            )
            row["objects"] = int(row["objects"]) + 1
            row["keys"].append(key)
        return list(buckets.values())
    except Exception:  # noqa: BLE001
        return []


def merge_quarantine_payloads(payloads: list[Any]) -> dict[str, Any]:
    """Fold small quarantine JSONs into one rewrite payload."""

    events: list[dict[str, Any]] = []
    sources = 0
    reason: str | None = None
    for payload in payloads:
        if isinstance(payload, bytes | bytearray | str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                sources += 1
                continue
        sources += 1
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    events.append(item)
                    reason = str(item.get("reason") or reason or "")
            continue
        if not isinstance(payload, dict):
            continue
        nested = payload.get("events") or payload.get("rejected")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    events.append(item)
            reason = str(payload.get("reason") or reason or "")
            continue
        events.append(payload)
        reason = str(payload.get("reason") or reason or "")
    return {
        "reason": reason or "",
        "record_count": len(events),
        "compacted_from": sources,
        "events": events,
    }


def _rewrite_prefix(
    settings: Settings,
    row: dict[str, Any],
) -> tuple[str | None, list[str], str | None]:
    """Write the compact object and delete sibling keys."""

    try:
        from lakehouse.aws import client
        from lakehouse.storage import put_json

        s3 = client("s3", settings)
        keys = list(row.get("keys") or [])
        payloads: list[Any] = []
        for key in keys:
            try:
                obj = s3.get_object(Bucket=settings.silver_bucket, Key=key)
                payloads.append(obj["Body"].read())
            except Exception:  # noqa: BLE001
                continue
        merged = merge_quarantine_payloads(payloads)
        merged["reason"] = str(row.get("reason") or merged.get("reason") or "")
        target = str(
            row.get("target") or compact_key(reason=str(row.get("reason") or "unknown"))
        )
        put_json(s3, settings.silver_bucket, target, merged)
        deleted: list[str] = []
        for key in keys:
            if key == target:
                continue
            s3.delete_object(Bucket=settings.silver_bucket, Key=key)
            deleted.append(key)
        return target, deleted, None
    except Exception as exc:  # noqa: BLE001
        return None, [], str(exc)


def collect_snapshot(
    settings: Settings | None = None,
    *,
    max_objects: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Spec plan plus a live quarantine plan when MiniStack answers."""

    spec = spec_snapshot(max_objects=max_objects)
    try:
        resolved = settings or load_settings()
    except Exception:  # noqa: BLE001
        return spec
    if not _endpoint_reachable(resolved.aws_endpoint_url):
        return spec

    live_parts = _live_quarantine_prefixes(resolved)
    if not live_parts:
        return spec

    plan = plan_compact(live_parts, max_objects=max_objects)
    rewritten: list[str] = []
    deleted: list[str] = []
    errors: list[str] = []
    if apply and plan["compact"]:
        for row in plan["compact"]:
            target, gone, err = _rewrite_prefix(resolved, row)
            if target:
                rewritten.append(target)
            deleted.extend(gone)
            if err:
                errors.append(f"{row.get('reason')}: {err}")
    return {
        "backend": "live",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": apply,
        "rewritten": rewritten,
        "deleted": deleted,
        "errors": errors,
        "spec": spec,
        **plan,
        "ok": not errors,
    }


def describe_quarantine_compact(
    *,
    max_objects: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    snap = collect_snapshot(max_objects=max_objects, apply=apply)
    return {
        "ok": bool(snap.get("ok")),
        "backend": snap.get("backend"),
        "dataset": snap.get("dataset", DATASET_ID),
        "max_objects": snap.get("max_objects"),
        "keep_count": snap.get("keep_count"),
        "compact_count": snap.get("compact_count"),
        "apply": snap.get("apply", False),
        "rewritten_count": len(list(snap.get("rewritten") or [])),
        "deleted_count": len(list(snap.get("deleted") or [])),
        "compact": snap.get("compact") or [],
    }
