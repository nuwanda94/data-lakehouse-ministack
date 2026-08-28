from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from lakehouse.config import Settings
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.silver import quarantine_key, silver_key
from lakehouse.silver.handler import transform_silver
from lakehouse.transforms.events import QuarantineRow


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
            {"Key": key}
            for (b, key) in self.objects
            if b == bucket and key.startswith(prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


class FakeDDB:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self.items.append(kwargs["Item"])
        return {}


VALID = {
    "event_id": "evt-1",
    "event_ts": "2026-01-02T12:00:00+00:00",
    "event_type": "purchase",
    "user_id": "user-001",
    "sku": "SKU-100",
    "quantity": 2,
    "amount_usd": 19.5,
    "country": "US",
}

INVALID = {
    "event_id": "evt-bad",
    "event_ts": "2026-01-02T12:00:00+00:00",
    "event_type": "explode",
    "user_id": "user-001",
    "sku": "SKU-100",
    "quantity": 1,
    "amount_usd": 1.0,
    "country": "US",
}


def test_event_driven_writes_silver_and_quarantine() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(Bucket="b", Key="events/dt=2026-01-02/evt-1.json", Body=json.dumps(VALID))
    s3.put_object(Bucket="b", Key="events/dt=2026-01-02/evt-bad.json", Body=json.dumps(INVALID))
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "events/dt=2026-01-02/evt-1.json"},
                },
            },
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "events/dt=2026-01-02/evt-bad.json"},
                },
            },
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "tmp/ignore.json"},
                },
            },
        ]
    }
    result = transform_silver(event, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "succeeded"
    # Seed-like timestamps from Jan 2026 are older than the 2-day lookback.
    assert result["valid"] + result["late"] == 1
    assert result["quarantined"] == 1
    assert result["metrics"]["silver_written"] == 1
    assert result["skipped"] == ["tmp/ignore.json"]
    expected_silver = silver_key(CommerceEvent.model_validate(VALID))
    assert expected_silver in result["silver_written"]
    assert ("s", expected_silver) in s3.objects
    qkey = quarantine_key(QuarantineRow(payload=INVALID, reason="unknown_event_type"))
    assert qkey in result["quarantine_written"]
    assert ddb.items[0]["zone"]["S"] == "silver"
    assert int(ddb.items[0]["valid"]["N"]) + int(ddb.items[0]["late"]["N"]) == 1
    assert ddb.items[0]["quarantined"]["N"] == "1"


def test_batch_mode_lists_bronze_prefix() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(Bucket="b", Key="events/dt=2026-01-02/evt-1.json", Body=json.dumps(VALID))
    result = transform_silver(None, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "succeeded"
    assert result["valid"] + result["late"] == 1
    assert len(result["silver_written"]) == 1


def test_all_missing_objects_fail_the_run() -> None:
    result = transform_silver(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "events/dt=2026-01-02/gone.json"},
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
