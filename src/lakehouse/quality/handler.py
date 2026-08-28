"""Quality-gate Lambda / local handler.

Reads Silver event JSON (event-driven S3/SQS refs or a batch list under
``events/``), evaluates the named quality gate, writes a report object, and
either fails the run or quarantines failing rows. Gold should only run after
a passed (or quarantined-and-cleaned) gate.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import unquote_plus

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.ingest.s3_events import extract_object_refs
from lakehouse.pipeline.runs import new_run
from lakehouse.pipeline.silver import quarantine_key
from lakehouse.quality.gate import QualityDecision, evaluate_quality
from lakehouse.transforms.events import QuarantineRow

LOGGER = logging.getLogger(__name__)

SILVER_PREFIX = "events/"
OnFail = Literal["fail", "quarantine"]


def _persist_run(
    ddb: Any,
    table: str,
    run: Any,
    *,
    metrics: dict[str, int],
    objects: list[str],
    quality: list[dict[str, Any]],
) -> None:
    item: dict[str, Any] = {
        "run_id": {"S": run.run_id},
        "status": {"S": run.status},
        "started_at": {"S": run.started_at.isoformat()},
        "zone": {"S": run.zone or "silver"},
        "object_count": {"N": str(len(objects))},
        "objects": {"S": json.dumps(objects)},
        "rows_scanned": {"N": str(metrics.get("rows_scanned", 0))},
        "rows_failed": {"N": str(metrics.get("rows_failed", 0))},
        "quarantine_written": {"N": str(metrics.get("quarantine_written", 0))},
        "quality": {"S": json.dumps(quality)},
    }
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
        return {"_raw": text, "event_id": ""}
    if isinstance(payload, dict):
        return payload
    return {"_raw": payload, "event_id": ""}


def _silver_keys_from_event(
    event: dict[str, Any] | None,
    *,
    default_bucket: str,
    s3: Any,
) -> tuple[list[tuple[str, str]], list[str]]:
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


def _write_quarantine(s3: Any, bucket: str, decision: QualityDecision) -> list[str]:
    written: list[str] = []
    for row in decision.failed_rows:
        qrow = QuarantineRow(payload=row.payload, reason="+".join(row.reasons) or "quality")
        key = quarantine_key(qrow)
        body = json.dumps({"reason": qrow.reason, "payload": qrow.payload, "checks": row.reasons})
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        written.append(key)
    return written


def _write_report(
    s3: Any,
    bucket: str,
    *,
    run_id: str,
    decision: QualityDecision,
) -> str:
    day = datetime.now(tz=UTC).date().isoformat()
    key = f"quality/dt={day}/run_id={run_id}.json"
    body = {
        "run_id": run_id,
        "passed": decision.passed,
        "action": decision.action,
        "rows_scanned": decision.rows_scanned,
        "rows_failed": decision.rows_failed,
        "fail_ratio": round(decision.fail_ratio, 4),
        "checks": [r.model_dump() for r in decision.results],
    }
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(body).encode("utf-8"),
        ContentType="application/json",
    )
    return key


def run_quality_gate(
    event: dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
    s3: Any | None = None,
    ddb: Any | None = None,
    on_fail: OnFail = "fail",
    max_fail_ratio: float = 0.0,
) -> dict[str, Any]:
    """Evaluate the quality gate over Silver objects and record a run."""

    resolved = settings or load_settings()
    s3_client = s3 or client("s3", resolved)
    ddb_client = ddb or client("dynamodb", resolved)

    pairs, skipped = _silver_keys_from_event(
        event, default_bucket=resolved.silver_bucket, s3=s3_client
    )

    records: list[dict[str, Any]] = []
    source_keys: list[str] = []
    missing: list[str] = []
    for bucket, key in pairs:
        payload = _load_json(s3_client, bucket, key)
        if payload is None:
            missing.append(f"{bucket}/{key}")
            continue
        records.append(payload)
        source_keys.append(key)

    run = new_run(zone="silver", status="running")
    decision = evaluate_quality(records, on_fail=on_fail, max_fail_ratio=max_fail_ratio)
    run.quality = decision.results

    quarantine_keys: list[str] = []
    if decision.action == "quarantine":
        quarantine_keys = _write_quarantine(s3_client, resolved.silver_bucket, decision)

    report_key = _write_report(
        s3_client, resolved.silver_bucket, run_id=run.run_id, decision=decision
    )

    metrics = {
        "rows_scanned": decision.rows_scanned,
        "rows_failed": decision.rows_failed,
        "quarantine_written": len(quarantine_keys),
    }

    if missing and not source_keys:
        run.status = "failed"
        run.error = f"missing silver objects: {', '.join(missing)}"
    elif not decision.passed and decision.action == "fail":
        run.status = "quality_failed"
        names = ", ".join(q.check_name for q in decision.failed_checks)
        run.error = f"quality gate failed: {names}"
    else:
        run.status = "succeeded"
    run.finished_at = datetime.now(tz=UTC)

    quality_payload = [q.model_dump() for q in decision.results]
    _persist_run(
        ddb_client,
        resolved.pipeline_runs_table,
        run,
        metrics=metrics,
        objects=source_keys,
        quality=quality_payload,
    )

    return {
        "run_id": run.run_id,
        "status": run.status,
        "passed": decision.passed,
        "action": decision.action,
        "accepted": source_keys,
        "skipped": skipped,
        "missing": missing,
        "rows_scanned": decision.rows_scanned,
        "rows_failed": decision.rows_failed,
        "fail_ratio": round(decision.fail_ratio, 4),
        "quality": quality_payload,
        "quarantine_written": quarantine_keys,
        "report_key": report_key,
        "error": run.error,
        "metrics": metrics,
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entrypoint (also used by the local CLI)."""

    _ = context
    return run_quality_gate(event)


def run_quality(*, settings: Settings | None = None, on_fail: OnFail = "fail") -> dict[str, Any]:
    """Batch mode: list every Silver event object and gate it."""

    return run_quality_gate(None, settings=settings, on_fail=on_fail)
