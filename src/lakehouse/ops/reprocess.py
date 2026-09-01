"""Reopen Gold partitions for a lookback window (late-arriving data).

Reads every Silver event whose Hive ``dt=`` partition falls inside
``[as_of - lookback, as_of]``, recomputes daily metrics from the *full*
partition (not just the late rows), and overwrites the matching Gold
object + DynamoDB metric row.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.gold.handler import _write_gold
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.idempotency import deterministic_run_id, idempotency_key
from lakehouse.pipeline.late import (
    affected_partitions,
    filter_events_in_window,
    key_in_window,
    window_bounds,
)
from lakehouse.pipeline.runs import new_run
from lakehouse.storage import list_keys, load_json
from lakehouse.transforms.events import aggregate_gold

SILVER_PREFIX = "events/"


def reprocess_gold_window(
    *,
    as_of: datetime | date | None = None,
    lookback_days: int | None = None,
    settings: Settings | None = None,
    s3: Any | None = None,
    ddb: Any | None = None,
) -> dict[str, Any]:
    """Rebuild Gold metrics for every Silver partition in the lookback window."""

    resolved = settings or load_settings()
    days = resolved.lookback_days if lookback_days is None else lookback_days
    start, end = window_bounds(as_of=as_of, lookback_days=days)
    s3_client = s3 or client("s3", resolved)
    ddb_client = ddb or client("dynamodb", resolved)

    all_keys = list_keys(s3_client, resolved.silver_bucket)
    window_keys = [key for key in all_keys if key_in_window(key, start=start, end=end)]

    events: list[CommerceEvent] = []
    invalid = 0
    late_flagged = 0
    for key in window_keys:
        payload = load_json(s3_client, resolved.silver_bucket, key)
        if payload is None:
            invalid += 1
            continue
        if payload.get("_late"):
            late_flagged += 1
        try:
            events.append(CommerceEvent.model_validate(payload))
        except Exception:  # noqa: BLE001
            invalid += 1

    in_window = filter_events_in_window(events, start=start, end=end)
    rows = aggregate_gold(in_window)
    written = _write_gold(
        s3_client,
        ddb_client,
        gold_bucket=resolved.gold_bucket,
        metrics_table=resolved.gold_metrics_table,
        rows=rows,
    )
    partitions = affected_partitions(in_window)

    fingerprint = [
        "reprocess",
        start.isoformat(),
        end.isoformat(),
        *window_keys,
    ]
    run_id = deterministic_run_id("gold", *fingerprint)
    key = idempotency_key("gold", *fingerprint)
    run = new_run(zone="gold", status="succeeded", run_id=run_id)
    run.finished_at = datetime.now(tz=UTC)
    ddb_client.put_item(
        TableName=resolved.pipeline_runs_table,
        Item={
            "run_id": {"S": run.run_id},
            "status": {"S": run.status},
            "started_at": {"S": run.started_at.isoformat()},
            "finished_at": {"S": run.finished_at.isoformat()},
            "zone": {"S": "gold"},
            "step": {"S": "reprocess"},
            "object_count": {"N": str(len(window_keys))},
            "objects": {"S": json.dumps(window_keys)},
            "idempotency_key": {"S": key},
            "metrics": {
                "S": json.dumps(
                    {
                        "lookback_days": days,
                        "window_start": start.isoformat(),
                        "window_end": end.isoformat(),
                        "silver_scanned": len(all_keys),
                        "silver_in_window": len(window_keys),
                        "late_flagged": late_flagged,
                        "skipped_invalid": invalid,
                        "gold_written": len(written),
                    }
                )
            },
        },
    )

    return {
        "run_id": run.run_id,
        "status": run.status,
        "lookback_days": days,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "silver_scanned": len(all_keys),
        "silver_in_window": window_keys,
        "late_flagged": late_flagged,
        "skipped_invalid": invalid,
        "partitions": partitions,
        "gold_written": written,
        "aggregates": rows,
        "idempotency_key": key,
    }
