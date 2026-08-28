"""Bronze ingestion Lambda / local handler.

Processes S3 object-created events (optionally delivered via SQS), HEAD/GETs
the Bronze object, and writes a pipeline-run row so the rest of the medallion
path has a consistent ``run_id``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote_plus

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.ingest.s3_events import BronzeObjectRef, extract_object_refs
from lakehouse.pipeline.runs import complete_run, new_run, persist_run

LOGGER = logging.getLogger(__name__)

BRONZE_PREFIX = "events/"


def _head_or_get(s3: Any, ref: BronzeObjectRef) -> dict[str, Any]:
    try:
        return s3.head_object(Bucket=ref.bucket, Key=ref.key)
    except Exception:  # noqa: BLE001 — MiniStack/AWS clients raise service errors
        return s3.get_object(Bucket=ref.bucket, Key=ref.key)


def ingest_bronze_event(
    event: dict[str, Any],
    *,
    settings: Settings | None = None,
    s3: Any | None = None,
    ddb: Any | None = None,
) -> dict[str, Any]:
    """Process one Lambda/SQS event batch and persist Bronze run metadata."""

    resolved = settings or load_settings()
    s3_client = s3 or client("s3", resolved)
    ddb_client = ddb or client("dynamodb", resolved)

    refs = extract_object_refs(event)
    accepted: list[BronzeObjectRef] = []
    skipped: list[str] = []
    missing: list[str] = []

    for ref in refs:
        key = unquote_plus(ref.key)
        if not key.startswith(BRONZE_PREFIX):
            skipped.append(key)
            continue
        try:
            _head_or_get(s3_client, BronzeObjectRef(bucket=ref.bucket, key=key))
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("bronze object missing %s/%s: %s", ref.bucket, key, exc)
            missing.append(f"{ref.bucket}/{key}")
            continue
        accepted.append(BronzeObjectRef(bucket=ref.bucket, key=key, source=ref.source))

    run = new_run(zone="bronze", status="running", step="ingest", event=event)
    object_keys = [ref.key for ref in accepted]
    if missing and not accepted:
        complete_run(
            run,
            status="failed",
            error=f"missing bronze objects: {', '.join(missing)}",
            objects=object_keys,
            metrics={"object_count": len(object_keys), "missing": len(missing)},
        )
    else:
        complete_run(
            run,
            status="succeeded",
            objects=object_keys,
            metrics={"object_count": len(object_keys), "missing": len(missing)},
        )
    persist_run(ddb_client, resolved.pipeline_runs_table, run)

    return {
        "run_id": run.run_id,
        "status": run.status,
        "accepted": object_keys,
        "skipped": skipped,
        "missing": missing,
        "records": len(refs),
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entrypoint (also used by the local CLI)."""

    _ = context
    return ingest_bronze_event(event)


def drain_bronze_queue(
    *,
    settings: Settings | None = None,
    max_messages: int = 10,
    wait_seconds: int = 1,
) -> dict[str, Any]:
    """Poll ``BRONZE_EVENTS_QUEUE`` and run the handler locally (MiniStack)."""

    resolved = settings or load_settings()
    sqs = client("sqs", resolved)
    queue_url = resolved.bronze_events_queue_url
    if not queue_url:
        resp = sqs.get_queue_url(QueueName=resolved.bronze_events_queue)
        queue_url = resp["QueueUrl"]

    received = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=min(max_messages, 10),
        WaitTimeSeconds=wait_seconds,
    )
    messages = received.get("Messages") or []
    results: list[dict[str, Any]] = []
    for message in messages:
        body = message.get("Body") or "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"Records": [{"eventSource": "aws:sqs", "body": body}]}
        if "Records" not in payload:
            payload = {"Records": [{"eventSource": "aws:sqs", "body": body}]}
        result = ingest_bronze_event(payload, settings=resolved)
        results.append(result)
        receipt = message.get("ReceiptHandle")
        if receipt:
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)

    return {
        "queue": resolved.bronze_events_queue,
        "polled": len(messages),
        "runs": results,
    }
