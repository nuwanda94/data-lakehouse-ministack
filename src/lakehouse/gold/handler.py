"""Gold aggregation Lambda / local handler.

Reads Silver event JSON, runs ``aggregate_gold``, writes one Hive-partitioned
object per (event_type, day) plus a matching DynamoDB row in the gold-metrics
table. Pipeline-run metadata lands in DynamoDB so operators can observe the
batch.
"""

from __future__ import annotations

import logging
from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.gold import gold_key
from lakehouse.pipeline.idempotency import (
    deterministic_run_id,
    idempotency_key,
    lookup_succeeded,
    replay_result,
)
from lakehouse.pipeline.runs import complete_run, new_run, persist_run
from lakehouse.storage import EVENTS_PREFIX, keys_from_event, load_pairs, put_json
from lakehouse.transforms.events import aggregate_gold

LOGGER = logging.getLogger(__name__)

SILVER_PREFIX = EVENTS_PREFIX


def _write_gold(
    s3: Any,
    ddb: Any,
    *,
    gold_bucket: str,
    metrics_table: str,
    rows: list[dict[str, Any]],
) -> list[str]:
    written: list[str] = []
    for row in rows:
        key = gold_key(metric=str(row["event_type"]), day=str(row["dt"]))
        put_json(s3, gold_bucket, key, row)
        ddb.put_item(
            TableName=metrics_table,
            Item={
                "metric_day": {"S": f"{row['event_type']}#{row['dt']}"},
                "event_type": {"S": str(row["event_type"])},
                "dt": {"S": str(row["dt"])},
                "events": {"N": str(int(row["events"]))},
                "amount_usd": {"N": str(row["amount_usd"])},
            },
        )
        written.append(key)
    return written


def transform_gold(
    event: dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
    s3: Any | None = None,
    ddb: Any | None = None,
) -> dict[str, Any]:
    """Aggregate Silver events into Gold objects + DynamoDB metrics."""

    resolved = settings or load_settings()
    s3_client = s3 or client("s3", resolved)
    ddb_client = ddb or client("dynamodb", resolved)

    pairs, skipped = keys_from_event(
        event, default_bucket=resolved.silver_bucket, s3=s3_client, prefix=SILVER_PREFIX
    )
    payloads, source_keys, missing = load_pairs(s3_client, pairs)

    events: list[CommerceEvent] = []
    invalid = 0
    for key, payload in zip(source_keys, payloads, strict=True):
        try:
            events.append(CommerceEvent.model_validate(payload))
        except Exception:  # noqa: BLE001
            invalid += 1
            LOGGER.warning("skipping unreadable silver object %s", key)

    fingerprint = [*source_keys, *[f"missing:{m}" for m in missing]]
    run_id = deterministic_run_id("gold", *fingerprint) if fingerprint else None
    key = idempotency_key("gold", *fingerprint) if fingerprint else None
    if run_id:
        existing = lookup_succeeded(ddb_client, resolved.pipeline_runs_table, run_id)
        if existing is not None:
            return replay_result(
                existing,
                skipped=skipped,
                missing=missing,
                silver_read=int(existing.metrics.get("silver_read", 0) or 0),
                skipped_invalid=int(existing.metrics.get("skipped_invalid", 0) or 0),
                gold_written=[],
                aggregates=[],
                idempotency_key=key,
            )

    run = new_run(zone="gold", status="running", run_id=run_id)
    rows = aggregate_gold(events)
    gold_keys = _write_gold(
        s3_client,
        ddb_client,
        gold_bucket=resolved.gold_bucket,
        metrics_table=resolved.gold_metrics_table,
        rows=rows,
    )

    metrics: dict[str, int | float | str] = {
        "silver_read": len(events),
        "skipped_invalid": invalid,
        "gold_written": len(gold_keys),
        "metrics_written": len(gold_keys),
    }
    if key:
        metrics["idempotency_key"] = key

    if missing and not source_keys:
        complete_run(
            run,
            status="failed",
            error=f"missing silver objects: {', '.join(missing)}",
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
        "silver_read": int(metrics["silver_read"]),
        "skipped_invalid": invalid,
        "gold_written": gold_keys,
        "aggregates": rows,
        "metrics": metrics,
        "idempotent_replay": False,
        "idempotency_key": key,
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entrypoint (also used by the local CLI)."""

    _ = context
    return transform_gold(event)


def run_gold(*, settings: Settings | None = None) -> dict[str, Any]:
    """Batch mode: list every Silver event object and aggregate it."""

    return transform_gold(None, settings=settings)
