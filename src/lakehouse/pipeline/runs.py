"""Pipeline run metadata — consistent run_id, status, metrics, errors in DynamoDB."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from lakehouse.models import PipelineRun, PipelineStatus, PipelineStep, QualityResult, Zone

_RESERVED = frozenset(
    {
        "run_id",
        "status",
        "started_at",
        "finished_at",
        "zone",
        "step",
        "parent_run_id",
        "error",
        "objects",
        "object_count",
        "quality",
        "metrics",
    }
)


def resolve_run_id(event: dict[str, Any] | None = None, explicit: str | None = None) -> str:
    """Prefer an explicit / event / env run_id so zone steps can share one id."""

    if explicit:
        return explicit
    if event:
        value = event.get("run_id") or event.get("pipeline_run_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    env = os.environ.get("LAKEHOUSE_RUN_ID") or os.environ.get("PIPELINE_RUN_ID")
    if env and env.strip():
        return env.strip()
    return str(uuid4())


def new_run(
    *,
    zone: Zone | None = None,
    status: PipelineStatus = "pending",
    step: PipelineStep | None = None,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    event: dict[str, Any] | None = None,
) -> PipelineRun:
    return PipelineRun(
        run_id=resolve_run_id(event, run_id),
        started_at=datetime.now(tz=UTC),
        status=status,
        zone=zone,
        step=step,
        parent_run_id=parent_run_id,
    )


def complete_run(
    run: PipelineRun,
    *,
    status: PipelineStatus,
    error: str | None = None,
    metrics: dict[str, int | float | str] | None = None,
    objects: list[str] | None = None,
    quality: list[QualityResult] | None = None,
) -> PipelineRun:
    run.status = status
    run.finished_at = datetime.now(tz=UTC)
    if error:
        run.error = error
    if metrics:
        run.metrics.update(metrics)
    if objects is not None:
        run.objects = objects
    if quality is not None:
        run.quality = quality
    return run


def run_to_item(run: PipelineRun) -> dict[str, Any]:
    """Encode a run as a DynamoDB attribute-value item."""

    item: dict[str, Any] = {
        "run_id": {"S": run.run_id},
        "status": {"S": run.status},
        "started_at": {"S": run.started_at.isoformat()},
    }
    if run.finished_at is not None:
        item["finished_at"] = {"S": run.finished_at.isoformat()}
    if run.zone:
        item["zone"] = {"S": run.zone}
    if run.step:
        item["step"] = {"S": run.step}
    if run.parent_run_id:
        item["parent_run_id"] = {"S": run.parent_run_id}
    if run.error:
        item["error"] = {"S": run.error}
    if run.objects:
        item["objects"] = {"S": json.dumps(run.objects)}
        item["object_count"] = {"N": str(len(run.objects))}
    else:
        item["object_count"] = {"N": "0"}
    if run.quality:
        item["quality"] = {"S": json.dumps([q.model_dump() for q in run.quality])}
    if run.metrics:
        item["metrics"] = {"S": json.dumps(run.metrics)}
        for key, value in run.metrics.items():
            if key in _RESERVED:
                continue
            if isinstance(value, bool):
                item[key] = {"BOOL": value}
            elif isinstance(value, int):
                item[key] = {"N": str(value)}
            elif isinstance(value, float):
                item[key] = {"N": str(value)}
            else:
                item[key] = {"S": str(value)}
    return item


def _attr_value(attr: dict[str, Any]) -> Any:
    if "S" in attr:
        return attr["S"]
    if "N" in attr:
        raw = attr["N"]
        return int(raw) if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()) else float(raw)
    if "BOOL" in attr:
        return attr["BOOL"]
    if "NULL" in attr:
        return None
    return attr


def item_to_run(item: dict[str, Any]) -> PipelineRun:
    """Decode a DynamoDB item into a PipelineRun."""

    def _s(name: str) -> str | None:
        raw = item.get(name)
        if not raw:
            return None
        return raw.get("S")

    started = _s("started_at") or datetime.now(tz=UTC).isoformat()
    finished = _s("finished_at")
    objects_raw = _s("objects")
    quality_raw = _s("quality")
    metrics_raw = _s("metrics")
    objects: list[str] = []
    if objects_raw:
        try:
            parsed = json.loads(objects_raw)
            if isinstance(parsed, list):
                objects = [str(x) for x in parsed]
        except json.JSONDecodeError:
            objects = []
    quality: list[QualityResult] = []
    if quality_raw:
        try:
            parsed = json.loads(quality_raw)
            if isinstance(parsed, list):
                quality = [QualityResult.model_validate(row) for row in parsed]
        except (json.JSONDecodeError, ValueError):
            quality = []
    metrics: dict[str, int | float | str] = {}
    if metrics_raw:
        try:
            parsed = json.loads(metrics_raw)
            if isinstance(parsed, dict):
                metrics = parsed
        except json.JSONDecodeError:
            metrics = {}
    if not metrics:
        for key, attr in item.items():
            if key in _RESERVED:
                continue
            value = _attr_value(attr) if isinstance(attr, dict) else attr
            if isinstance(value, (int, float, str)):
                metrics[key] = value

    zone = _s("zone")
    status = _s("status") or "pending"
    step = _s("step")
    return PipelineRun(
        run_id=_s("run_id") or "",
        started_at=datetime.fromisoformat(started),
        finished_at=datetime.fromisoformat(finished) if finished else None,
        status=status,  # type: ignore[arg-type]
        zone=zone if zone in {"bronze", "silver", "gold"} else None,
        step=step if step in {"ingest", "silver", "quality", "gold", "pipeline"} else None,
        parent_run_id=_s("parent_run_id"),
        quality=quality,
        error=_s("error"),
        objects=objects,
        metrics=metrics,
    )


def persist_run(ddb: Any, table: str, run: PipelineRun) -> dict[str, Any]:
    """Put a run item. Returns the encoded DynamoDB item."""

    item = run_to_item(run)
    ddb.put_item(TableName=table, Item=item)
    return item


def get_run(ddb: Any, table: str, run_id: str) -> PipelineRun | None:
    resp = ddb.get_item(TableName=table, Key={"run_id": {"S": run_id}})
    item = resp.get("Item")
    if not item:
        return None
    return item_to_run(item)


def list_runs(ddb: Any, table: str, *, limit: int = 50) -> list[PipelineRun]:
    resp = ddb.scan(TableName=table, Limit=limit)
    runs = [item_to_run(item) for item in resp.get("Items", []) or []]
    runs.sort(key=lambda r: r.started_at, reverse=True)
    return runs[:limit]


def run_as_dict(run: PipelineRun) -> dict[str, Any]:
    payload = run.model_dump(mode="json")
    payload["started_at"] = run.started_at.isoformat()
    payload["finished_at"] = run.finished_at.isoformat() if run.finished_at else None
    payload["quality"] = [q.model_dump() for q in run.quality]
    return payload
