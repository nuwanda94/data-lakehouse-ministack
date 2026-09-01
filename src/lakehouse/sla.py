"""Gold freshness SLA for the medallion lakehouse.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(Gold last-written vs a configurable max-age) and optionally folds in live
S3 LastModified / DynamoDB pipeline-run timestamps when MiniStack answers.

``python -m lakehouse sla`` prints JSON. Exit code 1 means the SLA is
breached. ``--max-age-hours`` overrides ``LAKEHOUSE_GOLD_SLA_HOURS``
(default 24).
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings

DEFAULT_MAX_AGE_HOURS = 24.0
DATASET_ID = "gold.daily_metrics"


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


def resolve_max_age_hours(explicit: float | None = None) -> float:
    if explicit is not None:
        return float(explicit)
    raw = os.environ.get("LAKEHOUSE_GOLD_SLA_HOURS")
    if raw and raw.strip():
        return float(raw)
    return DEFAULT_MAX_AGE_HOURS


def _age_hours(as_of: datetime, last_written: datetime) -> float:
    delta = as_of - last_written
    return round(delta.total_seconds() / 3600.0, 3)


def evaluate(
    *,
    last_written: datetime,
    as_of: datetime | None = None,
    max_age_hours: float | None = None,
    dataset: str = DATASET_ID,
    source: str = "spec",
) -> dict[str, Any]:
    """Compare last-written time against the freshness budget."""

    now = as_of or datetime.now(tz=UTC)
    if last_written.tzinfo is None:
        last_written = last_written.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    budget = resolve_max_age_hours(max_age_hours)
    age = _age_hours(now, last_written)
    ok = age <= budget
    return {
        "dataset": dataset,
        "source": source,
        "as_of": now.isoformat(),
        "last_written": last_written.isoformat(),
        "age_hours": age,
        "max_age_hours": budget,
        "status": "ok" if ok else "breached",
        "ok": ok,
    }


def spec_snapshot(
    *,
    as_of: datetime | None = None,
    max_age_hours: float | None = None,
    fresh: bool = True,
) -> dict[str, Any]:
    """Offline SLA used by unit tests and when MiniStack is down."""

    now = as_of or datetime.now(tz=UTC)
    budget = resolve_max_age_hours(max_age_hours)
    lag = 1.0 if fresh else budget + 2.0
    last_written = now - timedelta(hours=lag)
    check = evaluate(
        last_written=last_written,
        as_of=now,
        max_age_hours=budget,
        source="spec",
    )
    return {
        "backend": "spec",
        "generated_at": now.isoformat(),
        "checks": [check],
        "ok": check["ok"],
    }


def _live_gold_last_modified(settings: Settings) -> datetime | None:
    try:
        from lakehouse.aws import client
        from lakehouse.storage import list_keys

        s3 = client("s3", settings)
        keys = list_keys(s3, settings.gold_bucket, "metrics/")
        latest: datetime | None = None
        for key in keys:
            try:
                head = s3.head_object(Bucket=settings.gold_bucket, Key=key)
            except Exception:  # noqa: BLE001
                continue
            raw = head.get("LastModified")
            if not isinstance(raw, datetime):
                continue
            stamped = raw if raw.tzinfo else raw.replace(tzinfo=UTC)
            if latest is None or stamped > latest:
                latest = stamped
        return latest
    except Exception:  # noqa: BLE001
        return None


def _live_run_finished(settings: Settings) -> datetime | None:
    try:
        from lakehouse.ops.runs import query_runs

        payload = query_runs(settings=settings, limit=10)
        latest: datetime | None = None
        for row in payload.get("runs") or []:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "")
            if status not in {"succeeded", "success", "completed"}:
                continue
            raw = row.get("finished_at") or row.get("started_at")
            if raw is None:
                continue
            if isinstance(raw, datetime):
                stamped = raw if raw.tzinfo else raw.replace(tzinfo=UTC)
            else:
                try:
                    stamped = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                except ValueError:
                    continue
            if latest is None or stamped > latest:
                latest = stamped
        return latest
    except Exception:  # noqa: BLE001
        return None


def collect_snapshot(
    settings: Settings | None = None,
    *,
    as_of: datetime | None = None,
    max_age_hours: float | None = None,
) -> dict[str, Any]:
    """Spec check plus a live Gold check when MiniStack answers."""

    spec = spec_snapshot(as_of=as_of, max_age_hours=max_age_hours, fresh=True)
    resolved = settings or load_settings()
    if not _endpoint_reachable(resolved.aws_endpoint_url):
        return spec

    last_written = _live_gold_last_modified(resolved) or _live_run_finished(resolved)
    if last_written is None:
        return spec

    now = as_of or datetime.now(tz=UTC)
    live_check = evaluate(
        last_written=last_written,
        as_of=now,
        max_age_hours=max_age_hours,
        source="live",
    )
    return {
        "backend": "live",
        "generated_at": now.isoformat(),
        "checks": [live_check],
        "spec": spec,
        "ok": live_check["ok"],
    }


def describe_sla(
    *,
    max_age_hours: float | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    snap = collect_snapshot(as_of=as_of, max_age_hours=max_age_hours)
    checks = list(snap.get("checks") or [])
    primary = checks[0] if checks else {}
    return {
        "ok": bool(snap.get("ok")),
        "backend": snap.get("backend"),
        "dataset": primary.get("dataset", DATASET_ID),
        "status": primary.get("status", "unknown"),
        "age_hours": primary.get("age_hours"),
        "max_age_hours": primary.get("max_age_hours"),
        "last_written": primary.get("last_written"),
        "as_of": primary.get("as_of"),
        "check_count": len(checks),
    }
