from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from lakehouse.config import Settings
from lakehouse.gold.handler import transform_gold
from lakehouse.pipeline.gold import gold_key


def _settings() -> Settings:
    return Settings(
        aws_endpoint_url="http://localhost:4566",
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        bronze_bucket="b",
        silver_bucket="s",
        gold_bucket="g",
        pipeline_runs_table="runs",
        gold_metrics_table="metrics",
        bronze_events_queue="lakehouse-local-bronze-events",
        bronze_events_queue_url="",
    )


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        body = kwargs["Body"]
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = body
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = (kwargs["Bucket"], kwargs["Key"])
        if key not in self.objects:
            raise KeyError(key)
        return {"Body": BytesIO(self.objects[key])}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        prefix = kwargs.get("Prefix", "")
        bucket = kwargs["Bucket"]
        contents = [
            {"Key": key} for (b, key) in self.objects if b == bucket and key.startswith(prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


class FakeDDB:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self.items.append(kwargs["Item"])
        return {}


PURCHASE = {
    "event_id": "evt-1",
    "event_ts": "2026-01-02T12:00:00+00:00",
    "event_type": "purchase",
    "user_id": "user-001",
    "sku": "SKU-100",
    "quantity": 2,
    "amount_usd": 19.5,
    "country": "US",
    "_late": True,
}

VIEW = {
    "event_id": "evt-2",
    "event_ts": "2026-01-02T13:00:00+00:00",
    "event_type": "page_view",
    "user_id": "user-002",
    "sku": "SKU-100",
    "quantity": 1,
    "amount_usd": 0.0,
    "country": "US",
}

PURCHASE_2 = {
    "event_id": "evt-3",
    "event_ts": "2026-01-02T14:00:00+00:00",
    "event_type": "purchase",
    "user_id": "user-003",
    "sku": "SKU-200",
    "quantity": 1,
    "amount_usd": 10.5,
    "country": "US",
}


def test_event_driven_writes_gold_and_metrics() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(
        Bucket="s",
        Key="events/event_type=purchase/dt=2026-01-02/evt-1.json",
        Body=json.dumps(PURCHASE),
    )
    s3.put_object(
        Bucket="s",
        Key="events/event_type=page_view/dt=2026-01-02/evt-2.json",
        Body=json.dumps(VIEW),
    )
    s3.put_object(
        Bucket="s",
        Key="events/event_type=purchase/dt=2026-01-02/evt-3.json",
        Body=json.dumps(PURCHASE_2),
    )
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "s"},
                    "object": {"key": "events/event_type=purchase/dt=2026-01-02/evt-1.json"},
                },
            },
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "s"},
                    "object": {"key": "events/event_type=page_view/dt=2026-01-02/evt-2.json"},
                },
            },
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "s"},
                    "object": {"key": "events/event_type=purchase/dt=2026-01-02/evt-3.json"},
                },
            },
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "s"},
                    "object": {"key": "quarantine/reason=unknown_event_type/evt-bad.json"},
                },
            },
        ]
    }
    result = transform_gold(event, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "succeeded"
    assert result["silver_read"] == 3
    assert result["skipped"] == ["quarantine/reason=unknown_event_type/evt-bad.json"]
    purchase_key = gold_key(metric="purchase", day="2026-01-02")
    view_key = gold_key(metric="page_view", day="2026-01-02")
    assert purchase_key in result["gold_written"]
    assert view_key in result["gold_written"]
    purchase = json.loads(s3.objects[("g", purchase_key)])
    assert purchase["events"] == 2
    assert purchase["amount_usd"] == 30.0
    metric_items = [item for item in ddb.items if "metric_day" in item]
    run_items = [item for item in ddb.items if "run_id" in item]
    assert len(metric_items) == 2
    assert run_items[0]["zone"]["S"] == "gold"
    assert run_items[0]["gold_written"]["N"] == "2"


def test_batch_mode_lists_silver_prefix() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(
        Bucket="s",
        Key="events/event_type=purchase/dt=2026-01-02/evt-1.json",
        Body=json.dumps(PURCHASE),
    )
    s3.put_object(Bucket="s", Key="quarantine/reason=x/bad.json", Body=b"{}")
    result = transform_gold(None, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "succeeded"
    assert result["silver_read"] == 1
    assert len(result["gold_written"]) == 1


def test_all_missing_objects_fail_the_run() -> None:
    result = transform_gold(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "s3": {
                        "bucket": {"name": "s"},
                        "object": {"key": "events/event_type=purchase/dt=2026-01-02/gone.json"},
                    },
                }
            ]
        },
        settings=_settings(),
        s3=FakeS3(),
        ddb=FakeDDB(),
    )
    assert result["status"] == "failed"
    assert result["missing"]


def test_empty_silver_writes_no_gold() -> None:
    result = transform_gold(None, settings=_settings(), s3=FakeS3(), ddb=FakeDDB())
    assert result["status"] == "succeeded"
    assert result["gold_written"] == []
    assert result["aggregates"] == []
