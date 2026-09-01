"""Silver transform Lambda / local handler.

Reads Bronze JSON objects, runs ``cleanse_to_silver``, writes valid events
to the Silver bucket (Hive-style partitions) and quarantined payloads to a
``quarantine/`` prefix. Pipeline-run metadata + per-run metrics land in
DynamoDB so the Gold step and operators can observe the batch.
"""

from __future__ import annotations

from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.pipeline.idempotency import (
    deterministic_run_id,
    idempotency_key,
    lookup_succeeded,
    replay_result,
)
from lakehouse.pipeline.late import lookback_delta, watermark_from_event
from lakehouse.pipeline.runs import complete_run, new_run, persist_run
from lakehouse.pipeline.silver import quarantine_key, silver_key
from lakehouse.storage import EVENTS_PREFIX, keys_from_event, load_pairs, put_json
from lakehouse.transforms.events import SilverBatch, cleanse_to_silver

BRONZE_PREFIX = EVENTS_PREFIX


def _write_silver(s3: Any, bucket: str, batch: SilverBatch) -> tuple[list[str], list[str]]:
    silver_keys: list[str] = []
    quarantine_keys: list[str] = []
    for event in (*batch.valid, *batch.late):
        key = silver_key(event)
        payload = event.model_dump(mode="json")
        payload["_late"] = event in batch.late
        put_json(s3, bucket, key, payload)
        silver_keys.append(key)
    for row in batch.quarantined:
        key = quarantine_key(row)
        put_json(s3, bucket, key, {"reason": row.reason, "payload": row.payload})
        quarantine_keys.append(key)
    return silver_keys, quarantine_keys


def transform_silver(
    event: dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
    s3: Any | None = None,
    ddb: Any | None = None,
) -> dict[str, Any]:
    """Cleanse Bronze objects into Silver + quarantine and record a run."""

    resolved = settings or load_settings()
    s3_client = s3 or client("s3", resolved)
    ddb_client = ddb or client("dynamodb", resolved)

    pairs, skipped = keys_from_event(
        event, default_bucket=resolved.bronze_bucket, s3=s3_client, prefix=BRONZE_PREFIX
    )
    raw_records, source_keys, missing = load_pairs(s3_client, pairs)

    fingerprint = [*source_keys, *[f"missing:{m}" for m in missing]]
    run_id = deterministic_run_id("silver", *fingerprint) if fingerprint else None
    key = idempotency_key("silver", *fingerprint) if fingerprint else None
    if run_id:
        existing = lookup_succeeded(ddb_client, resolved.pipeline_runs_table, run_id)
        if existing is not None:
            return replay_result(
                existing,
                skipped=skipped,
                missing=missing,
                valid=int(existing.metrics.get("valid", 0) or 0),
                quarantined=int(existing.metrics.get("quarantined", 0) or 0),
                late=int(existing.metrics.get("late", 0) or 0),
                silver_written=[],
                quarantine_written=[],
                idempotency_key=key,
            )

    run = new_run(zone="silver", status="running", run_id=run_id)
    batch = cleanse_to_silver(
        raw_records,
        watermark=watermark_from_event(event),
        lookback=lookback_delta(resolved.lookback_days),
    )
    silver_keys, quarantine_keys = _write_silver(s3_client, resolved.silver_bucket, batch)

    metrics: dict[str, int | float | str] = {
        "valid": len(batch.valid),
        "quarantined": len(batch.quarantined),
        "late": len(batch.late),
        "silver_written": len(silver_keys),
        "quarantine_written": len(quarantine_keys),
        "lookback_days": resolved.lookback_days,
    }
    if key:
        metrics["idempotency_key"] = key

    if missing and not source_keys:
        complete_run(
            run,
            status="failed",
            error=f"missing bronze objects: {', '.join(missing)}",
            objects=source_keys,
            metrics=metrics,
        )
    else:
        complete_run(run, status="succeeded", objects=source_keys, metrics=metrics)
    persist_run(ddb_client, resolved.pipeline_runs_table, run)

    return {
        "run_id": run.run_id,
        "status": run.status,
        "accepted": source_keys,
        "skipped": skipped,
        "missing": missing,
        "valid": int(metrics["valid"]),
        "quarantined": int(metrics["quarantined"]),
        "late": int(metrics["late"]),
        "silver_written": silver_keys,
        "quarantine_written": quarantine_keys,
        "metrics": metrics,
        "idempotent_replay": False,
        "idempotency_key": key,
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entrypoint (also used by the local CLI)."""

    _ = context
    return transform_silver(event)


def run_silver(*, settings: Settings | None = None) -> dict[str, Any]:
    """Batch mode: list every Bronze object and transform it."""

    return transform_silver(None, settings=settings)
