"""Local Python runner: bronze JSON → silver JSON → gold aggregates."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.gold import gold_key
from lakehouse.pipeline.quality import run_quality_checks
from lakehouse.pipeline.runs import new_run
from lakehouse.pipeline.silver import silver_key


def _list_keys(s3: Any, bucket: str, prefix: str = "events/") -> list[str]:
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []) or []:
            keys.append(obj["Key"])
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys


def run_pipeline(*, settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or load_settings()
    s3 = client("s3", resolved)
    ddb = client("dynamodb", resolved)
    run = new_run(zone="silver", status="running")

    keys = _list_keys(s3, resolved.bronze_bucket)
    events: list[CommerceEvent] = []
    for key in keys:
        obj = s3.get_object(Bucket=resolved.bronze_bucket, Key=key)
        payload = json.loads(obj["Body"].read().decode("utf-8"))
        events.append(CommerceEvent.model_validate(payload))

    quality = run_quality_checks(events)
    failed = [q for q in quality if not q.passed]
    if failed:
        run.status = "quality_failed"
        run.finished_at = datetime.now(tz=UTC)
        run.quality = quality
        _persist_run(ddb, resolved.pipeline_runs_table, run)
        names = ", ".join(q.check_name for q in failed)
        raise RuntimeError(f"quality gate failed: {names}")

    silver_written = 0
    for event in events:
        key = silver_key(event)
        s3.put_object(
            Bucket=resolved.silver_bucket,
            Key=key,
            Body=event.model_dump_json().encode("utf-8"),
            ContentType="application/json",
        )
        silver_written += 1

    by_day_type: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"events": 0, "amount_usd": 0.0}
    )
    for event in events:
        day = event.event_ts.date().isoformat()
        bucket = by_day_type[(day, event.event_type)]
        bucket["events"] += 1
        bucket["amount_usd"] += event.amount_usd

    gold_written = 0
    for (day, event_type), stats in sorted(by_day_type.items()):
        key = gold_key(metric=event_type, day=day)
        body = json.dumps(
            {
                "dt": day,
                "event_type": event_type,
                "events": int(stats["events"]),
                "amount_usd": round(stats["amount_usd"], 2),
            }
        )
        s3.put_object(
            Bucket=resolved.gold_bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        ddb.put_item(
            TableName=resolved.gold_metrics_table,
            Item={
                "metric_day": {"S": f"{event_type}#{day}"},
                "event_type": {"S": event_type},
                "dt": {"S": day},
                "events": {"N": str(int(stats["events"]))},
                "amount_usd": {"N": str(round(stats["amount_usd"], 2))},
            },
        )
        gold_written += 1

    run.status = "succeeded"
    run.finished_at = datetime.now(tz=UTC)
    run.quality = quality
    run.zone = "gold"
    _persist_run(ddb, resolved.pipeline_runs_table, run)

    return {
        "run_id": run.run_id,
        "bronze_objects": len(keys),
        "silver_written": silver_written,
        "gold_written": gold_written,
        "quality": [q.model_dump() for q in quality],
    }


def _persist_run(ddb: Any, table: str, run: Any) -> None:
    item = {
        "run_id": {"S": run.run_id},
        "status": {"S": run.status},
        "started_at": {"S": run.started_at.isoformat()},
    }
    if run.finished_at is not None:
        item["finished_at"] = {"S": run.finished_at.isoformat()}
    if run.zone:
        item["zone"] = {"S": run.zone}
    if run.error:
        item["error"] = {"S": run.error}
    ddb.put_item(TableName=table, Item=item)
