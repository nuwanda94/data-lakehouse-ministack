"""Gold quarantine compact-after-retention (scheduled expire then compact).

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
that chains Gold quarantine TTL expiry and quarantine object compact,
then optionally folds in live MiniStack results.

Operators run gold-quarantine-retention and gold-quarantine-compact as
separate commands. ``gold-quarantine-maintain`` is the scheduled path:
expire objects older than the TTL window, then compact remaining
fragmented ``reason=/metric=/dt=`` prefixes.

``python -m lakehouse gold-quarantine-maintain`` prints JSON. Default is
dry-run (``apply=false``). Exit code 1 means either step reported
``ok=false``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from lakehouse.gold_quarantine_compact import (
    DEFAULT_MAX_OBJECTS,
    describe_gold_quarantine_compact,
    resolve_max_objects,
)
from lakehouse.gold_quarantine_compact import spec_snapshot as compact_spec
from lakehouse.gold_quarantine_retention import (
    DEFAULT_RETENTION_DAYS,
    describe_gold_quarantine_retention,
    resolve_retention_days,
)
from lakehouse.gold_quarantine_retention import spec_snapshot as retention_spec

DATASET_ID = "gold.quarantine"
JOB = "gold.quarantine.maintain"


def _as_date(as_of: date | datetime | None) -> date:
    if as_of is None:
        return datetime.now(tz=UTC).date()
    if isinstance(as_of, datetime):
        return as_of.date()
    return as_of


def spec_snapshot(
    *,
    as_of: date | datetime | None = None,
    retention_days: int | None = None,
    max_objects: int | None = None,
) -> dict[str, Any]:
    """Offline expire-then-compact plan used when MiniStack is down."""

    today = _as_date(as_of)
    expire = retention_spec(as_of=today, retention_days=retention_days)
    compact = compact_spec(max_objects=max_objects)
    return {
        "backend": "spec",
        "job": JOB,
        "dataset": DATASET_ID,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": False,
        "order": ["expire", "compact"],
        "retention_days": expire.get("retention_days"),
        "max_objects": compact.get("max_objects"),
        "expire_count": expire.get("expire_count"),
        "compact_count": compact.get("compact_count"),
        "expire": expire.get("expire") or [],
        "compact": compact.get("compact") or [],
        "ok": True,
    }


def collect_snapshot(
    *,
    as_of: date | datetime | None = None,
    retention_days: int | None = None,
    max_objects: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Run Gold quarantine retention first, then compact."""

    today = _as_date(as_of)
    spec = spec_snapshot(
        as_of=today,
        retention_days=retention_days,
        max_objects=max_objects,
    )
    expire = describe_gold_quarantine_retention(
        retention_days=retention_days,
        as_of=today,
        apply=apply,
    )
    compact = describe_gold_quarantine_compact(
        max_objects=max_objects,
        apply=apply,
    )
    live = expire.get("backend") == "live" or compact.get("backend") == "live"
    errors: list[str] = []
    if not expire.get("ok"):
        errors.append("retention failed")
    if not compact.get("ok"):
        errors.append("compact failed")
    return {
        "backend": "live" if live else "spec",
        "job": JOB,
        "dataset": DATASET_ID,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": apply,
        "order": ["expire", "compact"],
        "retention_days": expire.get("retention_days") or resolve_retention_days(retention_days),
        "max_objects": compact.get("max_objects") or resolve_max_objects(max_objects),
        "expire_count": expire.get("expire_count"),
        "compact_count": compact.get("compact_count"),
        "deleted_count": expire.get("deleted_count"),
        "rewritten_count": compact.get("rewritten_count"),
        "expire": expire.get("expire") or [],
        "compact": compact.get("compact") or [],
        "retention": expire,
        "compaction": compact,
        "spec": spec,
        "errors": errors,
        "ok": not errors,
    }


def describe_gold_quarantine_maintain(
    *,
    as_of: date | datetime | None = None,
    retention_days: int | None = None,
    max_objects: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    snap = collect_snapshot(
        as_of=as_of,
        retention_days=retention_days,
        max_objects=max_objects,
        apply=apply,
    )
    return {
        "ok": bool(snap.get("ok")),
        "backend": snap.get("backend"),
        "job": JOB,
        "dataset": DATASET_ID,
        "order": snap.get("order"),
        "retention_days": snap.get("retention_days") or DEFAULT_RETENTION_DAYS,
        "max_objects": snap.get("max_objects") or DEFAULT_MAX_OBJECTS,
        "expire_count": snap.get("expire_count"),
        "compact_count": snap.get("compact_count"),
        "apply": snap.get("apply", False),
        "deleted_count": snap.get("deleted_count") or 0,
        "rewritten_count": snap.get("rewritten_count") or 0,
        "expire": snap.get("expire") or [],
        "compact": snap.get("compact") or [],
    }
