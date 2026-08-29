"""Gold aggregation Lambda / local handler.

Reads Silver event JSON, runs ``aggregate_gold``, writes one Hive-partitioned
object per (event_type, day) plus a matching DynamoDB row in the gold-metrics
table. Pipeline-run metadata lands in DynamoDB so operators can observe the
batch. Packaging the function as a Terraform Lambda zip remains a later chore.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote_plus

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.ingest.s3_events import extract_object_refs
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.gold import gold_key
from lakehouse.pipeline.idempotency import (
    deterministic_run_id,
    idempotency_key,
    lookup_succeeded,
    replay_result,
)
from lakehouse.pipeline.runs import new_run
from lakehouse.transforms.events import aggregate_gold

LOGGER = logging.getLogger(__name__)

SILVER_PREFIX = "events/"


def _persist_run(
    ddb: Any,
    table: str,
    run: Any,
    *,
    metrics: dict[str, int | str],
    objects: list[str],
) -> None:
    item: dict[str, Any] = {
        "run_id": {"S": run.run_id},
        "status": {"S": run.status},
        "started_at": {"S": run.started_at.isoformat()},
        "zone": {"S": run.zone or "gold"},
        "object_count": {"N": str(len(objects))},
        "objects": {"S": json.dumps(objects)},
        "silver_read": {"N": str(metrics.get("silver_read", 0))},
        "skipped_invalid": {"N": str(metrics.get("skipped_invalid", 0))},
        "gold_written": {"N": str(metrics.get("gold_written", 0))},
        "metrics_written": {"N": str(metrics.get("metrics_written", 0))},
    }
    if metrics.get("idempotency_key"):
        item["idempotency_key"] = {"S": str(metrics["idempotency_key"])}
        item["metrics"] = {"S": json.dumps(metrics)}
    if run.finished_at is not None:
        item["finished_at"] = {"S": run.finished_at.isoformat()}
    if run.error:
        item["error"] = {"S": run.error}
    ddb.put_item(TableName=table, Item=item)


def _list_silver_keys(s3: Any, bucket: str, prefix: str = SILVER_PREFIX) -> list[str]:
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []) or []:
            key = obj["Key"]
            if key.endswith("/"):
                continue
            keys.append(key)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys


def _load_json(s3: Any, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("silver object missing %s/%s: %s", bucket, key, exc)
        return None
    body = obj["Body"].read()
    if isinstance(body, bytes):
        text = body.decode("utf-8")
    else:
        text = str(body)
    text = text.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}
    if isinstance(payload, dict):
        return payload
    return {"_raw": payload}


def _silver_keys_from_event(
    event: dict[str, Any] | None,
    *,
    default_bucket: str,
    s3: Any,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (bucket, key) pairs plus skipped keys."""

    if not event:
        return [(default_bucket, key) for key in _list_silver_keys(s3, default_bucket)], []

    refs = extract_object_refs(event)
    if not refs:
        return [(default_bucket, key) for key in _list_silver_keys(s3, default_bucket)], []

    accepted: list[tuple[str, str]] = []
    skipped: list[str] = []
    for ref in refs:
        key = unquote_plus(ref.key)
        if not key.startswith(SILVER_PREFIX):
            skipped.append(key)
            continue
        accepted.append((ref.bucket or default_bucket, key))
    return accepted, skipped


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
        s3.put_object(
            Bucket=gold_bucket,
            Key=key,
            Body=json.dumps(row).encode("utf-8"),
            ContentType="application/json",
        )
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

    pairs, skipped = _silver_keys_from_event(
        event, default_bucket=resolved.silver_bucket, s3=s3_client
    )

    events: list[CommerceEvent] = []
    source_keys: list[str] = []
    missing: list[str] = []
    invalid = 0
    for bucket, key in pairs:
        payload = _load_json(s3_client, bucket, key)
        if payload is None:
            missing.append(f"{bucket}/{key}")
            continue
        source_keys.append(key)
        try:
            events.append(CommerceEvent.model_validate(payload))
        except Exception:  # noqa: BLE001
            invalid += 1
            LOGGER.warning("skipping unreadable silver object %s/%s", bucket, key)

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

    metrics: dict[str, int | str] = {
        "silver_read": len(events),
        "skipped_invalid": invalid,
        "gold_written": len(gold_keys),
        "metrics_written": len(gold_keys),
    }
    if key:
        metrics["idempotency_key"] = key

    if missing and not source_keys:
        run.status = "failed"
        run.error = f"missing silver objects: {', '.join(missing)}"
    else:
        run.status = "succeeded"
    run.finished_at = datetime.now(tz=UTC)
    _persist_run(
        ddb_client,
        resolved.pipeline_runs_table,
        run,
        metrics=metrics,
        objects=source_keys,
    )

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
