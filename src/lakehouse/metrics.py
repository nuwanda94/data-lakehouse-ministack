"""Structured pipeline metrics (CloudWatch + in-process).

Zone handlers already persist counters on the DynamoDB run row. This module
adds a first-class catalog of custom metrics, an in-process recorder used by
tests and ``python -m lakehouse metrics``, and a best-effort
``cloudwatch:PutMetricData`` path when ``FEATURE_EMIT_METRICS`` is on.

MiniStack may not emulate CloudWatch. PutMetricData failures are swallowed
so the medallion path never depends on metrics availability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from lakehouse.config import Settings, load_settings

NAMESPACE = "Lakehouse/Medallion"

# Assumed average object size used as an Athena / S3 scan cost proxy.
BYTES_PER_RECORD = 2048
BYTES_PER_GOLD_OBJECT = 8192

METRIC_CATALOG: tuple[dict[str, str], ...] = (
    {
        "name": "RecordsProcessed",
        "unit": "Count",
        "description": "Rows or objects accepted by a zone step",
    },
    {
        "name": "QualityFailures",
        "unit": "Count",
        "description": "Rows that failed the Silver quality gate",
    },
    {
        "name": "QualityFailRatio",
        "unit": "None",
        "description": "Failed rows / scanned rows for a quality run",
    },
    {
        "name": "LateEvents",
        "unit": "Count",
        "description": "Silver events behind the lookback watermark",
    },
    {
        "name": "PipelineLagSeconds",
        "unit": "Seconds",
        "description": "Seconds between the latest event_ts and run finish",
    },
    {
        "name": "EstimatedBytes",
        "unit": "Bytes",
        "description": "Cost proxy: records * 2KiB + gold objects * 8KiB",
    },
    {
        "name": "ObjectsWritten",
        "unit": "Count",
        "description": "S3 objects written by the zone",
    },
    {
        "name": "RunDurationMilliseconds",
        "unit": "Milliseconds",
        "description": "Wall-clock duration of the zone handler",
    },
)


@dataclass(frozen=True, slots=True)
class MetricPoint:
    name: str
    value: float
    unit: str
    zone: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    dimensions: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload

    def cloudwatch_datum(self) -> dict[str, Any]:
        dims = [{"Name": "Zone", "Value": self.zone}]
        for key, value in self.dimensions.items():
            if key == "Zone":
                continue
            dims.append({"Name": key, "Value": str(value)})
        return {
            "MetricName": self.name,
            "Value": float(self.value),
            "Unit": self.unit,
            "Timestamp": self.timestamp,
            "Dimensions": dims,
        }


_BUFFER: list[MetricPoint] = []


def reset_metrics() -> None:
    """Drop in-process points (used by tests)."""

    _BUFFER.clear()


def recorded_metrics() -> list[MetricPoint]:
    return list(_BUFFER)


def metric_catalog() -> list[dict[str, str]]:
    return [dict(item) for item in METRIC_CATALOG]


def _unit_for(name: str) -> str:
    for item in METRIC_CATALOG:
        if item["name"] == name:
            return item["unit"]
    return "None"


def record(
    name: str,
    value: float | int,
    *,
    zone: str,
    unit: str | None = None,
    timestamp: datetime | None = None,
    dimensions: dict[str, str] | None = None,
) -> MetricPoint:
    point = MetricPoint(
        name=name,
        value=float(value),
        unit=unit or _unit_for(name),
        zone=zone,
        timestamp=timestamp or datetime.now(tz=UTC),
        dimensions=dimensions or {},
    )
    _BUFFER.append(point)
    return point


def estimated_bytes(*, records: int = 0, gold_objects: int = 0) -> int:
    return max(0, records) * BYTES_PER_RECORD + max(0, gold_objects) * BYTES_PER_GOLD_OBJECT


def points_from_run(
    *,
    zone: str,
    metrics: dict[str, Any],
    status: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    latest_event_ts: datetime | None = None,
) -> list[MetricPoint]:
    """Map a zone handler metrics dict onto the catalog."""

    now = finished_at or datetime.now(tz=UTC)
    dims = {"Status": status or "unknown"}
    points: list[MetricPoint] = []

    records = _first_int(
        metrics,
        "valid",
        "rows_scanned",
        "silver_read",
        "object_count",
        "records",
    )
    points.append(record("RecordsProcessed", records, zone=zone, timestamp=now, dimensions=dims))

    quality_fail = _first_int(metrics, "rows_failed", "quarantined")
    if zone in {"quality", "silver"} or quality_fail:
        points.append(
            record("QualityFailures", quality_fail, zone=zone, timestamp=now, dimensions=dims)
        )

    scanned = _first_int(metrics, "rows_scanned", "valid")
    if zone == "quality" and scanned >= 0:
        ratio = (quality_fail / scanned) if scanned else 0.0
        raw_ratio = metrics.get("fail_ratio")
        if isinstance(raw_ratio, int | float) and not isinstance(raw_ratio, bool):
            ratio = float(raw_ratio)
        points.append(record("QualityFailRatio", ratio, zone=zone, timestamp=now, dimensions=dims))

    late = _first_int(metrics, "late")
    if zone == "silver" or late:
        points.append(record("LateEvents", late, zone=zone, timestamp=now, dimensions=dims))

    written = _first_int(
        metrics,
        "gold_written",
        "silver_written",
        "metrics_written",
        "objects_written",
    )
    points.append(record("ObjectsWritten", written, zone=zone, timestamp=now, dimensions=dims))

    bytes_proxy = estimated_bytes(records=records, gold_objects=written if zone == "gold" else 0)
    points.append(record("EstimatedBytes", bytes_proxy, zone=zone, timestamp=now, dimensions=dims))

    if started_at is not None:
        duration_ms = max(0.0, (now - started_at).total_seconds() * 1000.0)
        points.append(
            record(
                "RunDurationMilliseconds",
                duration_ms,
                zone=zone,
                timestamp=now,
                dimensions=dims,
            )
        )

    if latest_event_ts is not None:
        event_ts = latest_event_ts
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=UTC)
        lag = max(0.0, (now - event_ts).total_seconds())
        points.append(record("PipelineLagSeconds", lag, zone=zone, timestamp=now, dimensions=dims))

    return points


def emit_points(
    points: list[MetricPoint],
    *,
    settings: Settings | None = None,
    cloudwatch: Any | None = None,
) -> dict[str, Any]:
    """Best-effort PutMetricData. Always returns a summary."""

    resolved = settings or load_settings()
    payload = {
        "namespace": NAMESPACE,
        "emitted": 0,
        "buffered": len(points),
        "backend": "buffer",
        "enabled": bool(resolved.feature_emit_metrics),
        "error": None,
        "metrics": [p.as_dict() for p in points],
    }
    if not points or not resolved.feature_emit_metrics:
        return payload

    try:
        cw = cloudwatch
        if cw is None:
            from lakehouse.aws import client

            cw = client("cloudwatch", resolved)
        cw.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[p.cloudwatch_datum() for p in points],
        )
        payload["emitted"] = len(points)
        payload["backend"] = "cloudwatch"
    except Exception as exc:  # noqa: BLE001 — MiniStack often has no CW API
        payload["error"] = str(exc)
        payload["backend"] = "buffer"
    return payload


def emit_run_metrics(
    *,
    zone: str,
    metrics: dict[str, Any],
    status: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    latest_event_ts: datetime | None = None,
    settings: Settings | None = None,
    cloudwatch: Any | None = None,
) -> dict[str, Any]:
    """Record + optionally publish metrics for one zone run. Never raises."""

    try:
        points = points_from_run(
            zone=zone,
            metrics=metrics,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            latest_event_ts=latest_event_ts,
        )
        return emit_points(points, settings=settings, cloudwatch=cloudwatch)
    except Exception as exc:  # noqa: BLE001
        return {
            "namespace": NAMESPACE,
            "emitted": 0,
            "buffered": 0,
            "backend": "error",
            "enabled": False,
            "error": str(exc),
            "metrics": [],
        }


def describe_metrics(*, settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or load_settings()
    return {
        "namespace": NAMESPACE,
        "enabled": bool(resolved.feature_emit_metrics),
        "catalog": metric_catalog(),
        "buffered": [p.as_dict() for p in recorded_metrics()],
        "cost_proxy": {
            "bytes_per_record": BYTES_PER_RECORD,
            "bytes_per_gold_object": BYTES_PER_GOLD_OBJECT,
        },
    }


def _first_int(metrics: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key not in metrics:
            continue
        value = metrics[key]
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, list):
            return len(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0
