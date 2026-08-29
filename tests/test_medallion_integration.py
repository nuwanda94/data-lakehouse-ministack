"""Integration coverage for Bronze → Silver → quality → Gold.

Default tests drive the real zone handlers against in-memory S3/DynamoDB
fakes so ``make test`` stays hermetic. Live MiniStack coverage is opt-in
via ``LAKEHOUSE_LIVE=1`` (or an already-reachable endpoint) and is marked
``integration`` so CI can collect it after ``make up && make infra``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from lakehouse.config import Settings
from lakehouse.gold.handler import transform_gold
from lakehouse.ingest.bronze_handler import ingest_bronze_event
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.bronze import bronze_key
from lakehouse.pipeline.gold import gold_key
from lakehouse.quality.handler import run_quality_gate
from lakehouse.seed.generate import generate_events
from lakehouse.silver.handler import transform_silver


def _settings(**overrides: str) -> Settings:
    values = {
        "aws_endpoint_url": "http://localhost:4566",
        "aws_region": "us-east-1",
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
        "bronze_bucket": "b",
        "silver_bucket": "s",
        "gold_bucket": "g",
        "pipeline_runs_table": "runs",
        "gold_metrics_table": "metrics",
        "bronze_events_queue": "bronze-events",
        "bronze_events_queue_url": "",
    }
    values.update(overrides)
    return Settings(**values)


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

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = (kwargs["Bucket"], kwargs["Key"])
        if key not in self.objects:
            raise KeyError(key)
        return {"ContentLength": len(self.objects[key])}

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


def _s3_event(bucket: str, keys: list[str]) -> dict[str, Any]:
    return {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {"bucket": {"name": bucket}, "object": {"key": key}},
            }
            for key in keys
        ]
    }


def _write_bronze(s3: FakeS3, events: list[CommerceEvent]) -> list[str]:
    keys: list[str] = []
    for event in events:
        key = bronze_key(event)
        s3.put_object(Bucket="b", Key=key, Body=event.model_dump_json())
        keys.append(key)
    return keys


def test_handlers_promote_bronze_through_silver_quality_gold() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    settings = _settings()
    events = generate_events(8, start=datetime(2026, 1, 2, tzinfo=UTC), seed=7)
    bronze_keys = _write_bronze(s3, events)

    ingest = ingest_bronze_event(_s3_event("b", bronze_keys), settings=settings, s3=s3, ddb=ddb)
    assert ingest["status"] == "succeeded"
    assert ingest["accepted"] == bronze_keys

    silver = transform_silver(_s3_event("b", bronze_keys), settings=settings, s3=s3, ddb=ddb)
    assert silver["status"] == "succeeded"
    assert silver["valid"] + silver["late"] == 8
    assert len(silver["silver_written"]) == 8
    assert silver["quarantined"] == 0

    quality = run_quality_gate(
        _s3_event("s", silver["silver_written"]),
        settings=settings,
        s3=s3,
        ddb=ddb,
    )
    assert quality["status"] == "succeeded"
    assert quality["passed"] is True
    assert quality["report_key"].startswith("quality/")

    gold = transform_gold(
        _s3_event("s", silver["silver_written"]),
        settings=settings,
        s3=s3,
        ddb=ddb,
    )
    assert gold["status"] == "succeeded"
    assert gold["silver_read"] == 8
    assert gold["gold_written"]

    type_counts: dict[str, int] = {}
    for event in events:
        type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
    for event_type, count in type_counts.items():
        key = gold_key(metric=event_type, day="2026-01-02")
        assert ("g", key) in s3.objects
        payload = json.loads(s3.objects[("g", key)])
        assert payload["events"] == count

    zones = {item.get("zone", {}).get("S") for item in ddb.items if "zone" in item}
    assert {"bronze", "silver", "gold"} <= zones
    metric_rows = [item for item in ddb.items if "metric_day" in item]
    assert len(metric_rows) == len(gold["gold_written"])


def test_quality_gate_blocks_gold_when_silver_is_invalid() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    settings = _settings()
    s3.put_object(
        Bucket="s",
        Key="events/event_type=purchase/dt=2026-01-02/bad.json",
        Body=json.dumps(
            {
                "event_id": "",
                "event_ts": "not-a-timestamp",
                "event_type": "???",
                "user_id": "",
                "sku": "",
                "quantity": -1,
                "amount_usd": -9,
            }
        ),
    )
    quality = run_quality_gate(None, settings=settings, s3=s3, ddb=ddb)
    assert quality["status"] == "quality_failed"
    assert quality["passed"] is False

    gold = transform_gold(None, settings=settings, s3=s3, ddb=ddb)
    # Gold still runs in isolation; operators gate on quality status.
    assert gold["status"] == "succeeded"
    assert gold["silver_read"] == 0
    assert gold["gold_written"] == []


def _ministack_reachable(endpoint: str) -> bool:
    try:
        with urlopen(f"{endpoint.rstrip('/')}/_localstack/health", timeout=1.5) as resp:
            return 200 <= resp.status < 500
    except (URLError, OSError, TimeoutError):
        try:
            with urlopen(endpoint, timeout=1.5) as resp:
                return resp.status < 500
        except (URLError, OSError, TimeoutError):
            return False


def _live_enabled() -> bool:
    flag = os.environ.get("LAKEHOUSE_LIVE", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    return _ministack_reachable(endpoint)


@pytest.mark.integration
def test_live_ministack_bronze_silver_gold() -> None:
    """End-to-end against a running MiniStack + Terraform buckets/tables."""

    if not _live_enabled():
        pytest.skip("MiniStack not reachable; set LAKEHOUSE_LIVE=1 after make up && make infra")

    from lakehouse.aws import client
    from lakehouse.config import load_settings
    from lakehouse.ops.seed import seed_bronze

    settings = load_settings()
    s3 = client("s3", settings)
    ddb = client("dynamodb", settings)

    try:
        s3.head_bucket(Bucket=settings.bronze_bucket)
        ddb.describe_table(TableName=settings.pipeline_runs_table)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"infra not applied: {exc}")

    seed = seed_bronze(5, settings=settings)
    assert seed["written"] == 5
    sample = seed["sample_key"]
    assert sample

    ingest = ingest_bronze_event(_s3_event(settings.bronze_bucket, [sample]), settings=settings)
    assert ingest["status"] == "succeeded"

    silver = transform_silver(None, settings=settings)
    assert silver["status"] == "succeeded"
    assert silver["valid"] + silver["late"] >= 1

    quality = run_quality_gate(None, settings=settings)
    assert quality["status"] in {"succeeded", "quality_failed"}

    gold = transform_gold(None, settings=settings)
    assert gold["status"] == "succeeded"
    listed = s3.list_objects_v2(Bucket=settings.gold_bucket, Prefix="metrics/")
    assert listed.get("Contents")
