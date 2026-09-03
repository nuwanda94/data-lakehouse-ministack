"""Gold quarantine partition retention / TTL.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(Gold Hive ``quarantine/reason=…/metric=…/dt=YYYY-MM-DD`` keys vs a
configurable retention window) and optionally folds in live S3 objects
when MiniStack answers.

``python -m lakehouse gold-quarantine-retention`` prints JSON. Default is
dry-run (``apply=false``). Exit code 1 means expired partitions exist and
``--apply`` was requested but a delete failed.

Retention days come from ``LAKEHOUSE_GOLD_QUARANTINE_RETENTION_DAYS``
(default 30) or ``--retention-days``.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings
from lakehouse.partitions import parse_hive_key

DEFAULT_RETENTION_DAYS = 30
DATASET_ID = "gold.quarantine"
PREFIX = "quarantine/"


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
    raw = os.environ.get("LAKEHOUSE_GOLD_QUARANTINE_RETENTION_DAYS")
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
    metric: str | None = None,
    reason: str | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    """Mark one Gold quarantine partition as keep or expire."""

    if isinstance(dt, str):
        parsed = date.fromisoformat(dt)
    else:
        parsed = dt
    cutoff = cutoff_date(as_of, retention_days)
    expired = parsed < cutoff
    age_days = (as_of - parsed).days
    return {
        "dataset": DATASET_ID,
        "reason": reason,
        "metric": metric,
        "dt": parsed.isoformat(),
        "key": key,
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
    """Classify a list of ``{dt, metric?, reason?, key?}`` partitions."""

    today = as_of or datetime.now(tz=UTC).date()
    budget = resolve_retention_days(retention_days)
    rows = [
        classify_partition(
            dt=str(item.get("dt") or ""),
            as_of=today,
            retention_days=budget,
            metric=item.get("metric"),
            reason=item.get("reason"),
            key=item.get("key"),
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
    stale = today - timedelta(days=budget + 10)
    week = today - timedelta(days=7)
    fixtures = [
        {
            "reason": "unreadable_silver",
            "metric": "purchase",
            "dt": today.isoformat(),
            "key": (
                f"quarantine/reason=unreadable_silver/metric=purchase/"
                f"dt={today.isoformat()}/part-000.json"
            ),
        },
        {
            "reason": "non_positive_events",
            "metric": "purchase",
            "dt": week.isoformat(),
            "key": (
                f"quarantine/reason=non_positive_events/metric=purchase/"
                f"dt={week.isoformat()}/part-000.json"
            ),
        },
        {
            "reason": "unknown_event_type",
            "metric": "page_view",
            "dt": stale.isoformat(),
            "key": (
                f"quarantine/reason=unknown_event_type/metric=page_view/"
                f"dt={stale.isoformat()}/part-000.json"
            ),
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


def _live_gold_quarantine_partitions(settings: Settings) -> list[dict[str, Any]]:
    try:
        from lakehouse.aws import client
        from lakehouse.storage import list_keys

        s3 = client("s3", settings)
        keys = list_keys(s3, settings.gold_bucket, PREFIX)
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for key in keys:
            parts = parse_hive_key(key)
            dt = parts.get("dt")
            metric = parts.get("metric")
            reason = parts.get("reason")
            if not dt:
                continue
            token = (reason or "", metric or "", dt)
            if token in seen:
                continue
            seen.add(token)
            rows.append({"reason": reason, "metric": metric, "dt": dt, "key": key})
        return rows
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
            prefix = row.get("key")
            if not prefix:
                reason = row.get("reason")
                metric = row.get("metric")
                dt = row.get("dt")
                if reason and metric and dt:
                    prefix = f"quarantine/reason={reason}/metric={metric}/dt={dt}/"
                else:
                    continue
            folder = str(prefix)
            if not folder.endswith("/"):
                folder = folder.rsplit("/", 1)[0] + "/"
            try:
                keys = list_keys(s3, settings.gold_bucket, folder)
                for key in keys:
                    s3.delete_object(Bucket=settings.gold_bucket, Key=key)
                    deleted.append(key)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{folder}: {exc}")
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
    """Spec plan plus a live Gold quarantine plan when MiniStack answers."""

    spec = spec_snapshot(as_of=as_of, retention_days=retention_days)
    try:
        resolved = settings or load_settings()
    except Exception:  # noqa: BLE001
        return spec
    if not _endpoint_reachable(resolved.aws_endpoint_url):
        return spec

    live_parts = _live_gold_quarantine_partitions(resolved)
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


def describe_gold_quarantine_retention(
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
