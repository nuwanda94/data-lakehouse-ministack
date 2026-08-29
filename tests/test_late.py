"""Late-arriving window math and Gold reprocess."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any

from lakehouse.config import Settings, load_settings
from lakehouse.models import CommerceEvent
from lakehouse.ops.reprocess import reprocess_gold_window
from lakehouse.pipeline.gold import gold_key
from lakehouse.pipeline.late import (
    affected_partitions,
    dt_from_key,
    key_in_window,
    parse_lookback_days,
    window_bounds,
)
from lakehouse.pipeline.silver import silver_key


def _event(**overrides: object) -> CommerceEvent:
    base: dict[str, object] = dict(
        event_id="evt-ok",
        event_ts=datetime(2026, 1, 10, 12, tzinfo=UTC),
        event_type="purchase",
        user_id="user-001",
        sku="SKU-100",
        quantity=1,
        amount_usd=10.0,
        country="US",
    )
    base.update(overrides)
    return CommerceEvent.model_validate(base)


def test_parse_lookback_days_rejects_junk() -> None:
    assert parse_lookback_days(None) == 2
    assert parse_lookback_days("") == 2
    assert parse_lookback_days("7") == 7
    assert parse_lookback_days(-3) == 2
    assert parse_lookback_days("nope") == 2
    assert parse_lookback_days(0) == 0


def test_window_bounds_inclusive() -> None:
    start, end = window_bounds(as_of=date(2026, 1, 10), lookback_days=2)
    assert start == date(2026, 1, 8)
    assert end == date(2026, 1, 10)


def test_dt_from_key_and_window() -> None:
    key = "events/event_type=purchase/dt=2026-01-09/evt.json"
    assert dt_from_key(key) == "2026-01-09"
    assert key_in_window(key, start=date(2026, 1, 8), end=date(2026, 1, 10))
    assert not key_in_window(key, start=date(2026, 1, 10), end=date(2026, 1, 10))
    assert dt_from_key("events/no-partition.json") is None


def test_affected_partitions_unique_sorted() -> None:
    events = [
        _event(event_id="a", event_type="purchase", event_ts=datetime(2026, 1, 9, tzinfo=UTC)),
        _event(event_id="b", event_type="purchase", event_ts=datetime(2026, 1, 9, 8, tzinfo=UTC)),
        _event(event_id="c", event_type="refund", event_ts=datetime(2026, 1, 8, tzinfo=UTC)),
    ]
    assert affected_partitions(events) == [
        {"event_type": "purchase", "dt": "2026-01-09"},
        {"event_type": "refund", "dt": "2026-01-08"},
    ]


def test_load_settings_lookback_days(monkeypatch: object) -> None:
    monkeypatch.setenv("LOOKBACK_DAYS", "5")  # type: ignore[attr-defined]
    settings = load_settings(load_env_file=False)
    assert settings.lookback_days == 5


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
        bronze_events_queue="q",
        bronze_events_queue_url="",
        lookback_days=2,
    )


def test_reprocess_rebuilds_only_window_partitions() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    settings = _settings()

    inside = _event(event_id="in", event_ts=datetime(2026, 1, 9, 12, tzinfo=UTC), amount_usd=4.0)
    late = _event(event_id="late", event_ts=datetime(2026, 1, 8, 1, tzinfo=UTC), amount_usd=6.0)
    outside = _event(event_id="out", event_ts=datetime(2026, 1, 1, tzinfo=UTC), amount_usd=99.0)
    for event, flagged in ((inside, False), (late, True), (outside, False)):
        payload = event.model_dump(mode="json")
        payload["_late"] = flagged
        s3.put_object(
            Bucket="s",
            Key=silver_key(event),
            Body=json.dumps(payload).encode("utf-8"),
        )

    result = reprocess_gold_window(
        as_of=date(2026, 1, 10),
        lookback_days=2,
        settings=settings,
        s3=s3,
        ddb=ddb,
    )
    assert result["status"] == "succeeded"
    assert result["window_start"] == "2026-01-08"
    assert result["window_end"] == "2026-01-10"
    assert result["late_flagged"] == 1
    assert gold_key(metric="purchase", day="2026-01-09") in result["gold_written"]
    assert gold_key(metric="purchase", day="2026-01-08") in result["gold_written"]
    assert gold_key(metric="purchase", day="2026-01-01") not in result["gold_written"]
    amounts = {row["dt"]: row["amount_usd"] for row in result["aggregates"]}
    assert amounts["2026-01-09"] == 4.0
    assert amounts["2026-01-08"] == 6.0
    assert "2026-01-01" not in amounts
    gold_body = json.loads(s3.objects[("g", gold_key(metric="purchase", day="2026-01-08"))])
    assert gold_body["events"] == 1
    assert any(item.get("step", {}).get("S") == "reprocess" for item in ddb.items)
