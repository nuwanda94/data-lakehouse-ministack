"""Kinesis → Firehose → Bronze landing path.

Two backends:

* ``offline`` — in-memory encode / buffer / deliver. Used by unit tests
  and when MiniStack is down or Kinesis/Firehose are not enabled.
* ``live`` — ``PutRecords`` + ``PutRecordBatch`` against MiniStack (or
  AWS), then write the same events to Bronze so the existing S3 → SQS
  ingest path can pick them up.

``auto`` tries live and falls back to offline on any client error.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Literal

from lakehouse.models import CommerceEvent
from lakehouse.pipeline.bronze import bronze_key
from lakehouse.seed.generate import generate_events

StreamMode = Literal["auto", "live", "offline"]
StreamSink = Literal["kinesis", "firehose", "both"]


def encode_kinesis_record(event: CommerceEvent) -> dict[str, str]:
    """Shape one PutRecords entry: partition key = user_id."""

    payload = event.model_dump_json().encode("utf-8")
    return {
        "PartitionKey": event.user_id,
        "Data": base64.b64encode(payload).decode("ascii"),
    }


def encode_firehose_record(event: CommerceEvent) -> dict[str, str]:
    """Shape one PutRecordBatch entry (newline-delimited JSON body)."""

    line = event.model_dump_json() + "\n"
    return {"Data": base64.b64encode(line.encode("utf-8")).decode("ascii")}


def decode_stream_payload(data: str | bytes) -> dict[str, Any]:
    """Decode a Kinesis/Firehose Data field back to a JSON object."""

    if isinstance(data, bytes):
        raw = data
    else:
        text = data.strip()
        try:
            raw = base64.b64decode(text, validate=True)
        except Exception:  # noqa: BLE001 — accept raw JSON too
            raw = text.encode("utf-8")
    decoded = raw.decode("utf-8").strip()
    return json.loads(decoded)


def deliver_firehose_batch(
    events: list[CommerceEvent],
    *,
    prefix: str = "events",
) -> list[dict[str, Any]]:
    """Simulate Firehose S3 delivery: one Bronze object per event."""

    delivered: list[dict[str, Any]] = []
    for event in events:
        key = bronze_key(event, prefix=prefix)
        delivered.append(
            {
                "key": key,
                "event_id": event.event_id,
                "partition_key": event.user_id,
                "bytes": len(event.model_dump_json().encode("utf-8")),
            }
        )
    return delivered


def _offline_stream(count: int, sink: StreamSink) -> dict[str, Any]:
    events = generate_events(count)
    kinesis = [encode_kinesis_record(e) for e in events] if sink in {"kinesis", "both"} else []
    firehose = [encode_firehose_record(e) for e in events] if sink in {"firehose", "both"} else []
    delivered = deliver_firehose_batch(events)
    decoded = [decode_stream_payload(rec["Data"]) for rec in (kinesis or firehose)]
    return {
        "ok": True,
        "backend": "offline",
        "sink": sink,
        "produced": len(events),
        "kinesis_records": len(kinesis),
        "firehose_records": len(firehose),
        "bronze_objects": [row["key"] for row in delivered],
        "decoded_event_ids": [row["event_id"] for row in decoded],
        "live_errors": [],
    }


def _put_kinesis(events: list[CommerceEvent], stream_name: str, settings: Any) -> dict[str, Any]:
    from lakehouse.aws import client

    kinesis = client("kinesis", settings)
    records = [
        {
            "PartitionKey": e.user_id,
            "Data": e.model_dump_json().encode("utf-8"),
        }
        for e in events
    ]
    resp = kinesis.put_records(StreamName=stream_name, Records=records)
    failed = int(resp.get("FailedRecordCount") or 0)
    return {"put": len(records), "failed": failed}


def _put_firehose(events: list[CommerceEvent], delivery_name: str, settings: Any) -> dict[str, Any]:
    from lakehouse.aws import client

    firehose = client("firehose", settings)
    records = [{"Data": (e.model_dump_json() + "\n").encode("utf-8")} for e in events]
    resp = firehose.put_record_batch(DeliveryStreamName=delivery_name, Records=records)
    failed = int(resp.get("FailedPutCount") or 0)
    return {"put": len(records), "failed": failed}


def _write_bronze(events: list[CommerceEvent], settings: Any) -> list[str]:
    from lakehouse.aws import client

    s3 = client("s3", settings)
    keys: list[str] = []
    prefix = (settings.bronze_prefix or "events/").rstrip("/")
    for event in events:
        key = bronze_key(event, prefix=prefix)
        s3.put_object(
            Bucket=settings.bronze_bucket,
            Key=key,
            Body=event.model_dump_json().encode("utf-8"),
            ContentType="application/json",
        )
        keys.append(key)
    return keys


def _live_stream(count: int, sink: StreamSink) -> dict[str, Any]:
    from lakehouse.config import load_settings

    settings = load_settings()
    events = generate_events(count)
    live_errors: list[str] = []
    kinesis_put = 0
    firehose_put = 0

    stream_name = settings.kinesis_stream
    delivery_name = settings.firehose_stream

    if sink in {"kinesis", "both"}:
        try:
            result = _put_kinesis(events, stream_name, settings)
            kinesis_put = int(result["put"]) - int(result["failed"])
            if result["failed"]:
                live_errors.append(f"kinesis failed_record_count={result['failed']}")
        except Exception as exc:  # noqa: BLE001 — MiniStack may lack Kinesis
            live_errors.append(f"kinesis: {exc}")

    if sink in {"firehose", "both"}:
        try:
            result = _put_firehose(events, delivery_name, settings)
            firehose_put = int(result["put"]) - int(result["failed"])
            if result["failed"]:
                live_errors.append(f"firehose failed_put_count={result['failed']}")
        except Exception as exc:  # noqa: BLE001
            live_errors.append(f"firehose: {exc}")

    bronze_objects = _write_bronze(events, settings)
    return {
        "ok": True,
        "backend": "live",
        "sink": sink,
        "produced": len(events),
        "kinesis_records": kinesis_put if sink in {"kinesis", "both"} else 0,
        "firehose_records": firehose_put if sink in {"firehose", "both"} else 0,
        "bronze_objects": bronze_objects,
        "decoded_event_ids": [e.event_id for e in events],
        "live_errors": live_errors,
        "kinesis_stream": stream_name,
        "firehose_stream": delivery_name,
        "bronze_bucket": settings.bronze_bucket,
    }


def run_stream(
    count: int = 20,
    *,
    mode: StreamMode = "auto",
    sink: StreamSink = "both",
) -> dict[str, Any]:
    """Produce ``count`` events onto the streaming path."""

    if count < 0:
        raise ValueError("count must be >= 0")
    if mode not in {"auto", "live", "offline"}:
        raise ValueError(f"unknown mode: {mode}")
    if sink not in {"kinesis", "firehose", "both"}:
        raise ValueError(f"unknown sink: {sink}")

    if mode == "offline":
        return _offline_stream(count, sink)
    if mode == "live":
        return _live_stream(count, sink)

    try:
        return _live_stream(count, sink)
    except Exception as exc:  # noqa: BLE001
        fallback = _offline_stream(count, sink)
        fallback["live_errors"] = [str(exc)]
        fallback["fallback_from"] = "live"
        return fallback
