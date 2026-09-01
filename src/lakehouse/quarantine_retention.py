"""Silver quarantine retention / TTL.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(quarantine object ages vs a configurable TTL window) and optionally folds
in live Silver ``quarantine/`` objects when MiniStack answers.

``python -m lakehouse quarantine-retention`` prints JSON. Default is
dry-run (``apply=false``). Exit code 1 means expired objects exist and
``--apply`` was requested but a delete failed.

Retention days come from ``LAKEHOUSE_QUARANTINE_RETENTION_DAYS``
(default 14) or ``--retention-days``.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings

DEFAULT_RETENTION_DAYS = 14
DATASET_ID = "silver.quarantine"
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
    raw = os.environ.get("LAKEHOUSE_QUARANTINE_RETENTION_DAYS")
    if raw and raw.strip():
        return int(raw)
    return DEFAULT_RETENTION_DAYS


def cutoff_at(as_of: datetime, retention_days: int) -> datetime:
    """Oldest LastModified that is still inside the TTL window."""

    return as_of - timedelta(days=max(int(retention_days), 0))


def parse_quarantine_key(key: str) -> dict[str, str | None]:
    """Extract ``reason`` and ``event_id`` from a quarantine object key."""

    reason: str | None = None
    event_id: str | None = None
    parts = key.strip("/").split("/")
    for part in parts:
        if part.startswith("reason="):
            reason = part.split("=", 1)[1] or None
    if parts:
        leaf = parts[-1]
        if leaf.endswith(".json"):
            event_id = leaf[: -len(".json")] or None
    return {"reason": reason, "event_id": event_id}


def classify_object(
    *,
    written_at: datetime | str,
    as_of: datetime,
    retention_days: int,
    key: str | None = None,
    reason: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Mark one quarantine object as keep or expire."""

    if isinstance(written_at, str):
        parsed = datetime.fromisoformat(written_at.replace("Z", "+00:00"))
    else:
        parsed = written_at
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    as_aware = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
    cutoff = cutoff_at(as_aware, retention_days)
    expired = parsed < cutoff
    age_days = (as_aware - parsed).total_seconds() / 86400.0
    return {
        "dataset": DATASET_ID,
        "reason": reason,
        "event_id": event_id,
        "key": key,
        "written_at": parsed.isoformat(),
        "age_days": round(age_days, 3),
        "cutoff": cutoff.isoformat(),
        "action": "expire" if expired else "keep",
        "expired": expired,
    }


def plan_retention(
    objects: list[dict[str, Any]],
    *,
    as_of: datetime | None = None,
    retention_days: int | None = None,
) -> dict[str, Any]:
    """Classify a list of ``{written_at, key?, reason?, event_id?}`` rows."""

    now = as_of or datetime.now(tz=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    budget = resolve_retention_days(retention_days)
    rows = [
        classify_object(
            written_at=item["written_at"],
            as_of=now,
            retention_days=budget,
            key=item.get("key"),
            reason=item.get("reason"),
            event_id=item.get("event_id"),
        )
        for item in objects
        if item.get("written_at")
    ]
    expire = [row for row in rows if row["expired"]]
    keep = [row for row in rows if not row["expired"]]
    return {
        "dataset": DATASET_ID,
        "as_of": now.isoformat(),
        "retention_days": budget,
        "cutoff": cutoff_at(now, budget).isoformat(),
        "objects": rows,
        "keep_count": len(keep),
        "expire_count": len(expire),
        "expire": expire,
        "ok": True,
    }


def spec_snapshot(
    *,
    as_of: datetime | None = None,
    retention_days: int | None = None,
) -> dict[str, Any]:
    """Offline plan used by unit tests and when MiniStack is down."""

    now = as_of or datetime.now(tz=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    budget = resolve_retention_days(retention_days)
    fixtures = [
        {
            "reason": "schema",
            "event_id": "evt-keep-1",
            "written_at": now.isoformat(),
            "key": "quarantine/reason=schema/evt-keep-1.json",
        },
        {
            "reason": "missing_user",
            "event_id": "evt-keep-2",
            "written_at": (now - timedelta(days=2)).isoformat(),
            "key": "quarantine/reason=missing_user/evt-keep-2.json",
        },
        {
            "reason": "poison",
            "event_id": "evt-expire-1",
            "written_at": (now - timedelta(days=budget + 3)).isoformat(),
            "key": "quarantine/reason=poison/evt-expire-1.json",
        },
    ]
    plan = plan_retention(fixtures, as_of=now, retention_days=budget)
    return {
        "backend": "spec",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": False,
        "deleted": [],
        **plan,
    }


def _live_quarantine_objects(settings: Settings) -> list[dict[str, Any]]:
    try:
        from lakehouse.aws import client

        s3 = client("s3", settings)
        rows: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": settings.silver_bucket,
                "Prefix": PREFIX,
            }
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []) or []:
                key = obj.get("Key") or ""
                if not key or key.endswith("/"):
                    continue
                written = obj.get("LastModified")
                if written is None:
                    continue
                if getattr(written, "tzinfo", None) is None:
                    written = written.replace(tzinfo=UTC)
                meta = parse_quarantine_key(key)
                rows.append(
                    {
                        "key": key,
                        "written_at": written,
                        "reason": meta.get("reason"),
                        "event_id": meta.get("event_id"),
                    }
                )
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
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

        s3 = client("s3", settings)
        for row in expire:
            key = row.get("key")
            if not key:
                continue
            try:
                s3.delete_object(Bucket=settings.silver_bucket, Key=key)
                deleted.append(str(key))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{key}: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return deleted, errors


def collect_snapshot(
    settings: Settings | None = None,
    *,
    as_of: datetime | None = None,
    retention_days: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Spec plan plus a live Silver quarantine plan when MiniStack answers."""

    spec = spec_snapshot(as_of=as_of, retention_days=retention_days)
    try:
        resolved = settings or load_settings()
    except Exception:  # noqa: BLE001
        return spec
    if not _endpoint_reachable(resolved.aws_endpoint_url):
        return spec

    live_objs = _live_quarantine_objects(resolved)
    if not live_objs:
        return spec

    now = as_of or datetime.now(tz=UTC)
    plan = plan_retention(live_objs, as_of=now, retention_days=retention_days)
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


def describe_quarantine_retention(
    *,
    retention_days: int | None = None,
    as_of: datetime | None = None,
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
