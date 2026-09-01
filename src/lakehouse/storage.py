"""Shared S3 helpers used by Bronze / Silver / Gold / quality handlers.

Zone Lambdas previously each copied list-prefix, get-JSON, put-JSON, and
S3-event key extraction. Those live here so a layout or encoding change
happens once.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import unquote_plus

LOGGER = logging.getLogger(__name__)

EVENTS_PREFIX = "events/"


def list_keys(s3: Any, bucket: str, prefix: str = EVENTS_PREFIX) -> list[str]:
    """List object keys under ``prefix``, skipping folder placeholders."""

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


def load_json(s3: Any, bucket: str, key: str) -> dict[str, Any] | None:
    """GET an object and parse JSON. Missing objects return ``None``."""

    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("object missing %s/%s: %s", bucket, key, exc)
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


def put_json(s3: Any, bucket: str, key: str, payload: Any) -> str:
    """Serialize ``payload`` as UTF-8 JSON and PUT it."""

    if isinstance(payload, (bytes, bytearray)):
        body = bytes(payload)
    elif isinstance(payload, str):
        body = payload.encode("utf-8")
    else:
        body = json.dumps(payload).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    return key


def keys_from_event(
    event: dict[str, Any] | None,
    *,
    default_bucket: str,
    s3: Any,
    prefix: str = EVENTS_PREFIX,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ``(bucket, key)`` pairs plus skipped keys outside ``prefix``.

    An empty event lists every object under ``prefix`` on ``default_bucket``.
    """

    if not event:
        return [(default_bucket, key) for key in list_keys(s3, default_bucket, prefix)], []

    from lakehouse.ingest.s3_events import extract_object_refs

    refs = extract_object_refs(event)
    if not refs:
        return [(default_bucket, key) for key in list_keys(s3, default_bucket, prefix)], []

    accepted: list[tuple[str, str]] = []
    skipped: list[str] = []
    for ref in refs:
        key = unquote_plus(ref.key)
        if not key.startswith(prefix):
            skipped.append(key)
            continue
        accepted.append((ref.bucket or default_bucket, key))
    return accepted, skipped


def load_pairs(
    s3: Any,
    pairs: list[tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Load JSON for each ``(bucket, key)``. Returns records, keys, missing."""

    records: list[dict[str, Any]] = []
    source_keys: list[str] = []
    missing: list[str] = []
    for bucket, key in pairs:
        payload = load_json(s3, bucket, key)
        if payload is None:
            missing.append(f"{bucket}/{key}")
            continue
        records.append(payload)
        source_keys.append(key)
    return records, source_keys, missing
