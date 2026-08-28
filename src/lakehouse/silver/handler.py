"""Silver transform Lambda / local handler.

Reads Bronze JSON objects, runs ``cleanse_to_silver``, writes valid events
to the Silver bucket (Hive-style partitions) and quarantined payloads to a
``quarantine/`` prefix. Pipeline-run metadata + per-run metrics land in
DynamoDB so the Gold step and operators can observe the batch.
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
from lakehouse.pipeline.runs import new_run
from lakehouse.pipeline.silver import quarantine_key, silver_key
from lakehouse.transforms.events import SilverBatch, cleanse_to_silver

LOGGER = logging.getLogger(__name__)

BRONZE_PREFIX = "events/"


def _persist_run(
    ddb: Any,
    table: str,
    run: Any,
    *,
    metrics: dict[str, int],
    objects: list[str],
) -> None:
    item: dict[str, Any] = {
        "run_id": {"S": run.run_id},
        "status": {"S": run.status},
        "started_at": {"S": run.started_at.isoformat()},
        "zone": {"S": run.zone or "silver"},
        "object_count": {"N": str(len(objects))},
        "objects": {"S": json.dumps(objects)},
        "valid": {"N": str(metrics.get("valid", 0))},
        "quarantined": {"N": str(metrics.get("quarantined", 0))},
        "late": {"N": str(metrics.get("late", 0))},
        "silver_written": {"N": str(metrics.get("silver_written", 0))},
        "quarantine_written": {"N": str(metrics.get("quarantine_written", 0))},
    }
    if run.finished_at is not None:
        item["finished_at"] = {"S": run.finished_at.isoformat()}
    if run.error:
        item["error"] = {"S": run.error}
    ddb.put_item(TableName=table, Item=item)


def _list_bronze_keys(s3: Any, bucket: str, prefix: str = BRONZE_PREFIX) -> list[str]:
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
        LOGGER.warning("bronze object missing %s/%s: %s", bucket, key, exc)
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
        return {"_raw": text, "event_id": ""}
    if isinstance(payload, dict):
        return payload
    return {"_raw": payload, "event_id": ""}


def _write_silver(s3: Any, bucket: str, batch: SilverBatch) -> tuple[list[str], list[str]]:
    silver_keys: list[str] = []
    quarantine_keys: list[str] = []
    for event in (*batch.valid, *batch.late):
        key = silver_key(event)
        payload = event.model_dump(mode="json")
        payload["_late"] = event in batch.late
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json",
        )
        silver_keys.append(key)
    for row in batch.quarantined:
        key = quarantine_key(row)
        body = json.dumps({"reason": row.reason, "payload": row.payload})
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        quarantine_keys.append(key)
    return silver_keys, quarantine_keys


def _bronze_keys_from_event(
    event: dict[str, Any] | None,
    *,
    default_bucket: str,
    s3: Any,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (bucket, key) pairs plus skipped keys."""

    if not event:
        return [(default_bucket, key) for key in _list_bronze_keys(s3, default_bucket)], []

    refs = extract_object_refs(event)
    if not refs:
        return [(default_bucket, key) for key in _list_bronze_keys(s3, default_bucket)], []

    accepted: list[tuple[str, str]] = []
    skipped: list[str] = []
    for ref in refs:
        key = unquote_plus(ref.key)
        if not key.startswith(BRONZE_PREFIX):
            skipped.append(key)
            continue
        accepted.append((ref.bucket or default_bucket, key))
    return accepted, skipped


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

    pairs, skipped = _bronze_keys_from_event(
        event, default_bucket=resolved.bronze_bucket, s3=s3_client
    )

    raw_records: list[dict[str, Any]] = []
    source_keys: list[str] = []
    missing: list[str] = []
    for bucket, key in pairs:
        payload = _load_json(s3_client, bucket, key)
        if payload is None:
            missing.append(f"{bucket}/{key}")
            continue
        raw_records.append(payload)
        source_keys.append(key)

    run = new_run(zone="silver", status="running")
    batch = cleanse_to_silver(raw_records)
    silver_keys, quarantine_keys = _write_silver(s3_client, resolved.silver_bucket, batch)

    metrics = {
        "valid": len(batch.valid),
        "quarantined": len(batch.quarantined),
        "late": len(batch.late),
        "silver_written": len(silver_keys),
        "quarantine_written": len(quarantine_keys),
    }

    if missing and not source_keys:
        run.status = "failed"
        run.error = f"missing bronze objects: {', '.join(missing)}"
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
        "valid": metrics["valid"],
        "quarantined": metrics["quarantined"],
        "late": metrics["late"],
        "silver_written": silver_keys,
        "quarantine_written": quarantine_keys,
        "metrics": metrics,
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entrypoint (also used by the local CLI)."""

    _ = context
    return transform_silver(event)


def run_silver(*, settings: Settings | None = None) -> dict[str, Any]:
    """Batch mode: list every Bronze object and transform it."""

    return transform_silver(None, settings=settings)
