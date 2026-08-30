"""Athena partition projection and Hive partition helpers.

Silver and Gold objects already use Hive-style keys
(``event_type=…/dt=…`` and ``metric=…/dt=…``). Athena partition projection
lets Glue describe those keys without ``MSCK REPAIR TABLE`` / Glue
``CreatePartition`` calls — Athena expands the enum × date grid at query
time.

``projection.enabled`` plus ``storage.location.template`` live on the Glue
table parameters (Python catalog + Terraform ``glue.tf``). MiniStack does
not need a working Glue API; specs stay queryable locally.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from lakehouse.config import Settings, load_settings
from lakehouse.contracts import load_contract

EVENT_TYPES: tuple[str, ...] = ("page_view", "add_to_cart", "purchase", "refund")
DEFAULT_DT_START = "2024-01-01"
DEFAULT_DT_FORMAT = "yyyy-MM-dd"


def _enum_values(spec: dict[str, Any], field_name: str) -> tuple[str, ...]:
    for item in spec.get("fields") or []:
        if str(item.get("name")) == field_name:
            values = item.get("enum")
            if isinstance(values, list) and values:
                return tuple(str(v) for v in values)
    return EVENT_TYPES


def _prefix(spec: dict[str, Any], fallback: str) -> str:
    raw = str((spec.get("partitioning") or {}).get("prefix") or fallback)
    return raw.strip("/")


def silver_location_template(bucket: str, prefix: str = "events") -> str:
    cleaned = prefix.strip("/")
    return f"s3://{bucket}/{cleaned}/event_type=${{event_type}}/dt=${{dt}}"


def gold_location_template(bucket: str, prefix: str = "metrics") -> str:
    cleaned = prefix.strip("/")
    return f"s3://{bucket}/{cleaned}/metric=${{metric}}/dt=${{dt}}"


def projection_parameters(
    *,
    zone: str,
    bucket: str,
    prefix: str,
    enum_key: str,
    enum_values: tuple[str, ...] | list[str],
    date_key: str = "dt",
    date_start: str = DEFAULT_DT_START,
    date_end: str = "NOW",
) -> dict[str, str]:
    """Return Glue / Athena ``projection.*`` table parameters."""

    values = ",".join(enum_values)
    if zone == "gold":
        template = gold_location_template(bucket, prefix)
    else:
        template = silver_location_template(bucket, prefix)
    return {
        "projection.enabled": "true",
        f"projection.{enum_key}.type": "enum",
        f"projection.{enum_key}.values": values,
        f"projection.{date_key}.type": "date",
        f"projection.{date_key}.format": DEFAULT_DT_FORMAT,
        f"projection.{date_key}.range": f"{date_start},{date_end}",
        "storage.location.template": template,
    }


def silver_projection(settings: Settings | None = None) -> dict[str, str]:
    resolved = settings or load_settings()
    spec = load_contract("silver")
    prefix = _prefix(spec, resolved.silver_prefix)
    return projection_parameters(
        zone="silver",
        bucket=resolved.silver_bucket,
        prefix=prefix,
        enum_key="event_type",
        enum_values=_enum_values(spec, "event_type"),
    )


def gold_projection(settings: Settings | None = None) -> dict[str, str]:
    resolved = settings or load_settings()
    spec = load_contract("gold")
    prefix = _prefix(spec, resolved.gold_prefix)
    return projection_parameters(
        zone="gold",
        bucket=resolved.gold_bucket,
        prefix=prefix,
        enum_key="metric",
        enum_values=_enum_values(spec, "event_type"),
    )


def parse_hive_key(key: str) -> dict[str, str]:
    """Extract ``name=value`` segments from an S3 object key."""

    parts: dict[str, str] = {}
    for segment in key.strip("/").split("/"):
        if "=" in segment:
            name, value = segment.split("=", 1)
            if name and value:
                parts[name] = value
    return parts


def projected_partitions(
    *,
    enum_key: str,
    enum_values: tuple[str, ...] | list[str],
    date_key: str = "dt",
    start: date,
    end: date,
) -> list[dict[str, str]]:
    """Cartesian product of enum values × inclusive calendar dates."""

    if end < start:
        raise ValueError("end date must be on or after start date")
    rows: list[dict[str, str]] = []
    day = start
    while day <= end:
        iso = day.isoformat()
        for value in enum_values:
            rows.append({enum_key: str(value), date_key: iso})
        day += timedelta(days=1)
    return rows


def discover_s3_partitions(keys: list[str]) -> list[dict[str, str]]:
    """Unique Hive partitions present in a list of object keys."""

    seen: dict[tuple[tuple[str, str], ...], dict[str, str]] = {}
    for key in keys:
        parts = parse_hive_key(key)
        if not parts:
            continue
        token = tuple(sorted(parts.items()))
        seen[token] = parts
    return [seen[token] for token in sorted(seen)]


def describe_partitions(settings: Settings | None = None) -> dict[str, Any]:
    """Describe projection specs plus optional live S3 partition discovery."""

    resolved = settings or load_settings()
    silver_spec = load_contract("silver")
    gold_spec = load_contract("gold")
    types = _enum_values(silver_spec, "event_type")
    today = datetime.now(tz=UTC).date()
    window_start = today - timedelta(days=max(int(resolved.lookback_days), 0))
    payload: dict[str, Any] = {
        "strategy": "hive+projection",
        "event_types": list(types),
        "dt_range": {"start": DEFAULT_DT_START, "end": "NOW"},
        "silver": {
            "prefix": _prefix(silver_spec, resolved.silver_prefix),
            "hive": list((silver_spec.get("partitioning") or {}).get("hive") or []),
            "projection": silver_projection(resolved),
            "window": projected_partitions(
                enum_key="event_type",
                enum_values=types,
                start=window_start,
                end=today,
            ),
        },
        "gold": {
            "prefix": _prefix(gold_spec, resolved.gold_prefix),
            "hive": list((gold_spec.get("partitioning") or {}).get("hive") or []),
            "projection": gold_projection(resolved),
            "window": projected_partitions(
                enum_key="metric",
                enum_values=types,
                start=window_start,
                end=today,
            ),
        },
        "discovered": {"silver": [], "gold": []},
        "errors": [],
    }
    try:
        from lakehouse.aws import client

        s3 = client("s3", resolved)
        for zone, bucket, prefix in (
            ("silver", resolved.silver_bucket, payload["silver"]["prefix"]),
            ("gold", resolved.gold_bucket, payload["gold"]["prefix"]),
        ):
            resp = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/", MaxKeys=500)
            keys = [item["Key"] for item in resp.get("Contents") or [] if item.get("Key")]
            payload["discovered"][zone] = discover_s3_partitions(keys)
    except Exception as exc:  # pragma: no cover - MiniStack / missing creds
        payload["errors"].append(str(exc))
    return payload
