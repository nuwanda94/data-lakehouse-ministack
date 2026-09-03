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


def _live_gold_quarantine_partitions(settings: Settings) -> list[dict[str, Any]]:
    try:
        from lakehouse.aws import client
        from lakehouse.storage import list_keys

        s3 = client("s3", settings)
        keys = list_keys(s3, settings.gold_bucket, PREFIX)
        buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
        for key in keys:
            parts = parse_hive_key(key)
            dt = parts.get("dt")
            metric = parts.get("metric")
            reason = parts.get("reason")
            if not dt:
                continue
            token = (str(reason or "unknown"), str(metric or "unknown"), str(dt))
            row = buckets.setdefault(
                token,
                {
                    "reason": token[0],
                    "metric": token[1],
                    "dt": token[2],
                    "objects": 0,
                    "keys": [],
                },
            )
            row["objects"] = int(row["objects"]) + 1
            row["keys"].append(key)
        return list(buckets.values())
    except Exception:  # noqa: BLE001
        return []


def merge_quarantine_payloads(payloads: list[Any]) -> dict[str, Any]:
    """Fold small Gold quarantine JSONs into one rewrite payload."""

    events: list[dict[str, Any]] = []
    sources = 0
    reason: str | None = None
    metric: str | None = None
    dt: str | None = None
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
                    nested = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                    metric = str(
                        item.get("metric")
                        or item.get("event_type")
                        or nested.get("event_type")
                        or metric
                        or ""
                    )
                    dt = str(item.get("dt") or nested.get("dt") or dt or "")
            continue
        if not isinstance(payload, dict):
            continue
        nested_events = payload.get("events") or payload.get("rejected")
        if isinstance(nested_events, list):
            for item in nested_events:
                if isinstance(item, dict):
                    events.append(item)
            reason = str(payload.get("reason") or reason or "")
            metric = str(payload.get("metric") or payload.get("event_type") or metric or "")
            dt = str(payload.get("dt") or dt or "")
            continue
        events.append(payload)
        reason = str(payload.get("reason") or reason or "")
        inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        metric = str(
            payload.get("metric")
            or payload.get("event_type")
            or inner.get("event_type")
            or metric
            or ""
        )
        dt = str(payload.get("dt") or inner.get("dt") or dt or "")
    return {
        "reason": reason or "",
        "metric": metric or "unknown",
        "dt": dt or "",
        "zone": "gold",
        "record_count": len(events),
        "compacted_from": sources,
        "events": events,
    }


def _rewrite_partition(
    settings: Settings,
    row: dict[str, Any],
) -> tuple[str | None, list[str], str | None]:
    """Write the compact object and delete sibling keys."""

    try:
        from lakehouse.aws import client
        from lakehouse.storage import load_json, put_json

        s3 = client("s3", settings)
        keys = list(row.get("keys") or [])
        payloads: list[Any] = []
        for key in keys:
            try:
                payloads.append(load_json(s3, settings.gold_bucket, key))
            except Exception:  # noqa: BLE001
                continue
        merged = merge_quarantine_payloads(payloads)
        merged["reason"] = str(row.get("reason") or merged.get("reason") or "unknown")
        merged["metric"] = str(row.get("metric") or merged.get("metric") or "unknown")
        if not merged.get("dt"):
            merged["dt"] = str(row.get("dt") or "")
        target = str(
            row.get("target")
            or compact_key(
                reason=str(row.get("reason") or "unknown"),
                metric=str(row.get("metric") or "unknown"),
                dt=str(row.get("dt") or ""),
            )
        )
        put_json(s3, settings.gold_bucket, target, merged)
        deleted: list[str] = []
        for key in keys:
            if key == target:
                continue
            s3.delete_object(Bucket=settings.gold_bucket, Key=key)
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
    """Spec plan plus a live Gold quarantine plan when MiniStack answers."""

    spec = spec_snapshot(max_objects=max_objects)
    try:
        resolved = settings or load_settings()
    except Exception:  # noqa: BLE001
        return spec
    if not _endpoint_reachable(resolved.aws_endpoint_url):
        return spec

    live_parts = _live_gold_quarantine_partitions(resolved)
    if not live_parts:
        return spec

    plan = plan_compact(live_parts, max_objects=max_objects)
    rewritten: list[str] = []
    deleted: list[str] = []
    errors: list[str] = []
    if apply and plan["compact"]:
        for row in plan["compact"]:
            target, gone, err = _rewrite_partition(resolved, row)
            if target:
                rewritten.append(target)
            deleted.extend(gone)
            if err:
                errors.append(f"{row.get('reason')}/{row.get('metric')}/{row.get('dt')}: {err}")
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


def describe_gold_quarantine_compact(
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
