"""Read gold S3 objects and DynamoDB metrics for a quick local check."""

from __future__ import annotations

from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings


def query_gold(*, settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or load_settings()
    s3 = client("s3", resolved)
    ddb = client("dynamodb", resolved)

    gold_keys: list[str] = []
    resp = s3.list_objects_v2(Bucket=resolved.gold_bucket, Prefix="metrics/")
    for obj in resp.get("Contents", []) or []:
        gold_keys.append(obj["Key"])

    scan = ddb.scan(TableName=resolved.gold_metrics_table, Limit=50)
    metrics = []
    for item in scan.get("Items", []):
        metrics.append(
            {
                "metric_day": item.get("metric_day", {}).get("S"),
                "event_type": item.get("event_type", {}).get("S"),
                "dt": item.get("dt", {}).get("S"),
                "events": item.get("events", {}).get("N"),
                "amount_usd": item.get("amount_usd", {}).get("N"),
            }
        )

    return {
        "gold_bucket": resolved.gold_bucket,
        "gold_objects": gold_keys,
        "metrics": metrics,
    }
