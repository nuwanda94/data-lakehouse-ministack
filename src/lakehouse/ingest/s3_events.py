"""Parse native S3 notifications and SQS-wrapped S3 event payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_plus


@dataclass(frozen=True, slots=True)
class BronzeObjectRef:
    """A single Bronze object referenced by an S3 or SQS event."""

    bucket: str
    key: str
    event_name: str | None = None
    source: str = "s3"


def _decode_key(raw: str) -> str:
    return unquote_plus(raw)


def _from_s3_record(record: dict[str, Any], *, source: str) -> BronzeObjectRef | None:
    s3 = record.get("s3")
    if not isinstance(s3, dict):
        return None
    bucket_info = s3.get("bucket") or {}
    object_info = s3.get("object") or {}
    bucket = bucket_info.get("name")
    key = object_info.get("key")
    if not bucket or not key:
        return None
    return BronzeObjectRef(
        bucket=str(bucket),
        key=_decode_key(str(key)),
        event_name=record.get("eventName"),
        source=source,
    )


def _iter_s3_records(payload: Any, *, source: str) -> list[BronzeObjectRef]:
    refs: list[BronzeObjectRef] = []
    if not isinstance(payload, dict):
        return refs
    records = payload.get("Records")
    if not isinstance(records, list):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            bucket = (detail.get("bucket") or {}).get("name")
            key = (detail.get("object") or {}).get("key")
            if bucket and key:
                refs.append(
                    BronzeObjectRef(
                        bucket=str(bucket),
                        key=_decode_key(str(key)),
                        event_name=payload.get("detail-type"),
                        source="eventbridge",
                    )
                )
        return refs
    for record in records:
        if not isinstance(record, dict):
            continue
        ref = _from_s3_record(record, source=source)
        if ref is not None:
            refs.append(ref)
    return refs


def extract_object_refs(event: Any) -> list[BronzeObjectRef]:
    """Flatten S3, SQS-of-S3, and EventBridge payloads into object refs."""

    if not isinstance(event, dict):
        return []

    records = event.get("Records")
    if not isinstance(records, list):
        return _iter_s3_records(event, source="s3")

    refs: list[BronzeObjectRef] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        source = str(record.get("eventSource") or "")
        if source.endswith("sqs") or "body" in record:
            body = record.get("body")
            if isinstance(body, str):
                try:
                    nested = json.loads(body)
                except json.JSONDecodeError:
                    continue
                refs.extend(_iter_s3_records(nested, source="sqs"))
            elif isinstance(body, dict):
                refs.extend(_iter_s3_records(body, source="sqs"))
            continue
        ref = _from_s3_record(record, source="s3")
        if ref is not None:
            refs.append(ref)
    return refs
