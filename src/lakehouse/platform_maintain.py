"""Platform compact-after-retention (Bronze + Silver + Quarantine + Gold).

Operators can still run zone jobs separately. ``platform-maintain`` is the
scheduled path that walks every medallion zone plus Silver quarantine:

1. Bronze expire-then-compact
2. Silver expire-then-compact
3. Quarantine expire-then-compact
4. Gold expire-then-compact

Each zone expires Hive prefixes older than its retention window before
rewriting fragmented objects, so compact never rewrites objects the next
step would delete. Quarantine runs after Silver so cleaned events are
maintained before the failed-row side path.

``python -m lakehouse platform-maintain`` prints JSON. Default is dry-run
(``apply=false``). Exit code 1 means any zone reported ``ok=false``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from lakehouse.bronze_maintain import collect_snapshot as bronze_collect
from lakehouse.bronze_maintain import spec_snapshot as bronze_spec
from lakehouse.maintain import collect_snapshot as gold_collect
from lakehouse.maintain import spec_snapshot as gold_spec
from lakehouse.quarantine_maintain import collect_snapshot as quarantine_collect
from lakehouse.quarantine_maintain import spec_snapshot as quarantine_spec
from lakehouse.silver_maintain import collect_snapshot as silver_collect
from lakehouse.silver_maintain import spec_snapshot as silver_spec

JOB = "platform.maintain"
ZONES = ("bronze", "silver", "quarantine", "gold")
ORDER = [
    "bronze.maintain",
    "silver.maintain",
    "quarantine.maintain",
    "gold.maintain",
]


def spec_snapshot(*, as_of: date | None = None) -> dict[str, Any]:
    """Offline expire-then-compact plan used when MiniStack is down."""

    today = as_of or datetime.now(tz=UTC).date()
    as_of_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
    bronze = bronze_spec(as_of=today)
    silver = silver_spec(as_of=today)
    quarantine = quarantine_spec(as_of=as_of_dt)
    gold = gold_spec(as_of=today)
    zones = {
        "bronze": bronze,
        "silver": silver,
        "quarantine": quarantine,
        "gold": gold,
    }
    return {
        "backend": "spec",
        "job": JOB,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": False,
        "order": list(ORDER),
        "zones": list(ZONES),
        "expire_count": sum(int(z.get("expire_count") or 0) for z in zones.values()),
        "compact_count": sum(int(z.get("compact_count") or 0) for z in zones.values()),
        "bronze": bronze,
        "silver": silver,
        "quarantine": quarantine,
        "gold": gold,
        "ok": True,
    }


def collect_snapshot(
    *,
    as_of: date | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Run Bronze, Silver, Quarantine, then Gold maintain."""

    spec = spec_snapshot(as_of=as_of)
    today = as_of or datetime.now(tz=UTC).date()
    as_of_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
    bronze = bronze_collect(as_of=as_of, apply=apply)
    silver = silver_collect(as_of=as_of, apply=apply)
    quarantine = quarantine_collect(as_of=as_of_dt, apply=apply)
    gold = gold_collect(as_of=as_of, apply=apply)
    parts = (bronze, silver, quarantine, gold)
    live = any(z.get("backend") == "live" for z in parts)
    errors: list[str] = []
    if not bronze.get("ok"):
        errors.append("bronze maintain failed")
    if not silver.get("ok"):
        errors.append("silver maintain failed")
    if not quarantine.get("ok"):
        errors.append("quarantine maintain failed")
    if not gold.get("ok"):
        errors.append("gold maintain failed")
    return {
        "backend": "live" if live else "spec",
        "job": JOB,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "apply": apply,
        "order": list(ORDER),
        "zones": list(ZONES),
        "expire_count": (
            int(bronze.get("expire_count") or 0)
            + int(silver.get("expire_count") or 0)
            + int(quarantine.get("expire_count") or 0)
            + int(gold.get("expire_count") or 0)
        ),
        "compact_count": (
            int(bronze.get("compact_count") or 0)
            + int(silver.get("compact_count") or 0)
            + int(quarantine.get("compact_count") or 0)
            + int(gold.get("compact_count") or 0)
        ),
        "deleted_count": (
            int(bronze.get("deleted_count") or 0)
            + int(silver.get("deleted_count") or 0)
            + int(quarantine.get("deleted_count") or 0)
            + int(gold.get("deleted_count") or 0)
        ),
        "rewritten_count": (
            int(bronze.get("rewritten_count") or 0)
            + int(silver.get("rewritten_count") or 0)
            + int(quarantine.get("rewritten_count") or 0)
            + int(gold.get("rewritten_count") or 0)
        ),
        "bronze": bronze,
        "silver": silver,
        "quarantine": quarantine,
        "gold": gold,
        "spec": spec,
        "errors": errors,
        "ok": not errors,
    }


def describe_platform_maintain(
    *,
    as_of: date | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    snap = collect_snapshot(as_of=as_of, apply=apply)
    bronze = snap.get("bronze") or {}
    silver = snap.get("silver") or {}
    quarantine = snap.get("quarantine") or {}
    gold = snap.get("gold") or {}
    return {
        "ok": bool(snap.get("ok")),
        "backend": snap.get("backend"),
        "job": JOB,
        "order": snap.get("order"),
        "zones": snap.get("zones"),
        "expire_count": snap.get("expire_count"),
        "compact_count": snap.get("compact_count"),
        "apply": snap.get("apply", False),
        "deleted_count": snap.get("deleted_count") or 0,
        "rewritten_count": snap.get("rewritten_count") or 0,
        "bronze_job": bronze.get("job"),
        "silver_job": silver.get("job"),
        "quarantine_job": quarantine.get("job"),
        "gold_job": gold.get("job"),
    }
