"""Silver cleaned-event retention / TTL.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(Silver Hive ``events/event_type=/dt=YYYY-MM-DD`` keys vs a configurable
retention window) and optionally folds in live S3 objects when MiniStack
answers.

``python -m lakehouse silver-retention`` prints JSON. Default is dry-run
(``apply=false``). Exit code 1 means expired partitions exist and
``--apply`` was requested but a delete failed.

Retention days come from ``LAKEHOUSE_SILVER_RETENTION_DAYS`` (default 60)
or ``--retention-days``.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings
from lakehouse.partitions import parse_hive_key

DEFAULT_RETENTION_DAYS = 60
DATASET_ID = "silver.cleaned_events"
PREFIX = "events/"


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


def resolve_retention_days(explicit: int | None = None) -> int:
    if explicit is not None:
        return int(explicit)
    raw = os.environ.get("LAKEHOUSE_SILVER_RETENTION_DAYS")
    if raw and raw.strip():
        return int(raw)
    return DEFAULT_RETENTION_DAYS


def cutoff_date(as_of: date, retention_days: int) -> date:
    """Oldest ``dt`` that is still inside the retention window."""

    return as_of - timedelta(days=max(int(retention_days), 0))


def classify_partition(
    *,
    dt: date | str,
    as_of: date,
    retention_days: int,
    key: str | None = None,
    objects: int | None = None,
) -> dict[str, Any]:
    """Mark one Silver ``dt=`` partition as keep or expire."""

    if isinstance(dt, str):
        parsed = date.fromisoformat(dt)
    else:
        parsed = dt
    cutoff = cutoff_date(as_of, retention_days)
    expired = parsed < cutoff
    age_days = (as_of - parsed).days
    return {
        "dataset": DATASET_ID,
        "dt": parsed.isoformat(),
        "key": key,
        "objects": objects,
        "age_days": age_days,
        "cutoff": cutoff.isoformat(),
        "action": "expire" if expired else "keep",
        "expired": expired,
    }


def plan_retention(
    partitions: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    retention_days: int | None = None,
) -> dict[str, Any]:
    """Classify a list of ``{dt, key?, objects?}`` Silver partitions."""

    today = as_of or datetime.now(tz=UTC).date()
    budget = resolve_retention_days(retention_days)
    rows = [
        classify_partition(
            dt=str(item.get("dt") or ""),
            as_of=today,
            retention_days=budget,
            key=item.get("key"),
            objects=item.get("objects"),
        )
        for item in partitions
        if item.get("dt")
    ]
    expire = [row for row in rows if row["expired"]]
    keep = [row for row in rows if not row["expired"]]
    return {
        "dataset": DATASET_ID,
        "as_of": today.isoformat(),
        "retention_days": budget,
        "cutoff": cutoff_date(today, budget).isoformat(),
        "partitions": rows,
        "keep_count": len(keep),
        "expire_count": len(expire),
        "expire": expire,
        "ok": True,
    }


def spec_snapshot(
    *,
    as_of: date | None = None,
    retention_days: int | None = None,
) -> dict[str, Any]:
    """Offline plan used by unit tests and when MiniStack is down."""

    today = as_of or datetime.now(tz=UTC).date()
    budget = resolve_retention_days(retention_days)
    old = (today - timedelta(days=budget + 5)).isoformat()
    week = (today - timedelta(days=7)).isoformat()
    fixtures = [
        {
            "dt": today.isoformat(),
            "objects": 12,
            "key": (f"events/event_type=purchase/dt={today.isoformat()}/" "evt-keep-today.json"),
        },
        {
            "dt": week,
            "objects": 8,
            "key": f"events/event_type=purchase/dt={week}/evt-keep-week.json",
        },
        {
            "dt": old,
            "objects": 3,
            "key": f"events/event_type=purchase/dt={old}/evt-expire-old.json",
        },
    ]
    plan = plan_retention(fixtures, as_of=today, retention_days=budget)
    return {
        "backend": "spec",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": False,
        "deleted": [],
        **plan,
    }


def _live_silver_partitions(settings: Settings) -> list[dict[str, Any]]:
    try:
        from lakehouse.aws import client
        from lakehouse.storage import list_keys

        s3 = client("s3", settings)
        keys = list_keys(s3, settings.silver_bucket, PREFIX)
        buckets: dict[str, dict[str, Any]] = {}
        for key in keys:
            parts = parse_hive_key(key)
            dt = parts.get("dt")
            if not dt:
                continue
            row = buckets.setdefault(
                dt,
                {
                    "dt": dt,
                    "key": PREFIX,
                    "objects": 0,
                },
            )
            row["objects"] = int(row["objects"]) + 1
        return list(buckets.values())
    except Exception:  # noqa: BLE001
        return []


def _delete_expired(
    settings: Settings,
    expire: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    deleted: list[str] = []
    errors: list[str] = []
    try:
        from lakehouse.aws import client
        from lakehouse.storage import list_keys

        s3 = client("s3", settings)
        for row in expire:
            dt = str(row.get("dt") or "")
            if not dt:
                continue
            try:
                keys = list_keys(s3, settings.silver_bucket, PREFIX)
                for key in keys:
                    parts = parse_hive_key(key)
                    if parts.get("dt") != dt:
                        continue
                    s3.delete_object(Bucket=settings.silver_bucket, Key=key)
                    deleted.append(key)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{PREFIX}dt={dt}: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return deleted, errors


def collect_snapshot(
    settings: Settings | None = None,
    *,
    as_of: date | None = None,
    retention_days: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Spec plan plus a live Silver plan when MiniStack answers."""

    spec = spec_snapshot(as_of=as_of, retention_days=retention_days)
    try:
        resolved = settings or load_settings()
    except Exception:  # noqa: BLE001
        return spec
    if not _endpoint_reachable(resolved.aws_endpoint_url):
        return spec

    live_parts = _live_silver_partitions(resolved)
    if not live_parts:
        return spec

    today = as_of or datetime.now(tz=UTC).date()
    plan = plan_retention(live_parts, as_of=today, retention_days=retention_days)
    deleted: list[str] = []
    errors: list[str] = []
    if apply and plan["expire"]:
        deleted, errors = _delete_expired(resolved, plan["expire"])
    return {
        "backend": "live",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": apply,
        "deleted": deleted,
        "errors": errors,
        "spec": spec,
        **plan,
        "ok": not errors,
    }


def describe_silver_retention(
    *,
    retention_days: int | None = None,
    as_of: date | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    snap = collect_snapshot(
        as_of=as_of,
        retention_days=retention_days,
        apply=apply,
    )
    return {
        "ok": bool(snap.get("ok")),
        "backend": snap.get("backend"),
        "dataset": snap.get("dataset", DATASET_ID),
        "as_of": snap.get("as_of"),
        "retention_days": snap.get("retention_days"),
        "cutoff": snap.get("cutoff"),
        "keep_count": snap.get("keep_count"),
        "expire_count": snap.get("expire_count"),
        "apply": snap.get("apply", False),
        "deleted_count": len(list(snap.get("deleted") or [])),
        "expire": snap.get("expire") or [],
    }
