"""Unit tests for synthetic seed generation and bronze landing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from lakehouse.config import Settings
from lakehouse.ops.seed import seed_bronze
from lakehouse.pipeline.bronze import bronze_key
from lakehouse.seed.generate import generate_events


def test_generate_events_empty() -> None:
    assert generate_events(0) == []


def test_generate_events_rejects_negative_count() -> None:
    with pytest.raises(ValueError, match="count"):
        generate_events(-1)


def test_generate_events_deterministic_across_calls() -> None:
    a = generate_events(12, seed=42)
    b = generate_events(12, seed=42)
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]


def test_generate_events_seed_changes_sequence() -> None:
    a = generate_events(8, seed=1)
    b = generate_events(8, seed=2)
    assert [e.event_id for e in a] != [e.event_id for e in b]


def test_generate_events_event_ids_are_unique_and_stable() -> None:
    events = generate_events(25, seed=9)
    ids = [e.event_id for e in events]
    assert len(ids) == len(set(ids))
    assert ids[0] == "evt-0009-000000"
    assert ids[-1] == "evt-0009-000024"


def test_generate_events_uses_start_and_one_minute_cadence() -> None:
    start = datetime(2025, 12, 31, 23, 50, tzinfo=UTC)
    events = generate_events(15, start=start, seed=3)
    assert events[0].event_ts == start
    assert events[1].event_ts == start + timedelta(minutes=1)
    assert events[-1].event_ts == start + timedelta(minutes=14)
    days = {e.event_ts.date().isoformat() for e in events}
    assert "2025-12-31" in days
    assert "2026-01-01" in days


def test_generate_events_known_domains() -> None:
    events = generate_events(40, seed=11)
    assert {e.event_type for e in events} <= {"page_view", "add_to_cart", "purchase", "refund"}
    assert {e.sku for e in events} <= {"SKU-100", "SKU-200", "SKU-300", "SKU-400"}
    assert {e.country for e in events} <= {"US", "DE", "IN", "BR", "JP"}
    assert all(e.quantity >= 1 for e in events)
    assert all(e.amount_usd > 0 for e in events)


def test_bronze_key_follows_dt_partition() -> None:
    event = generate_events(1, start=datetime(2026, 2, 3, tzinfo=UTC), seed=1)[0]
    assert bronze_key(event) == f"events/dt=2026-02-03/{event.event_id}.json"


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        body = kwargs["Body"]
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = body
        return {}


def _settings() -> Settings:
    return Settings(
        aws_endpoint_url="http://localhost:4566",
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        bronze_bucket="bronze-test",
        silver_bucket="s",
        gold_bucket="g",
        pipeline_runs_table="runs",
        gold_metrics_table="metrics",
        bronze_events_queue="bronze-events",
        bronze_events_queue_url="",
    )


def test_seed_bronze_empty_writes_nothing(monkeypatch: Any) -> None:
    fake = _FakeS3()
    monkeypatch.setattr("lakehouse.ops.seed.client", lambda *a, **k: fake)
    result = seed_bronze(0, settings=_settings())
    assert result["written"] == 0
    assert result["sample_key"] is None
    assert fake.objects == {}


def test_seed_bronze_writes_partitioned_json(monkeypatch: Any) -> None:
    fake = _FakeS3()
    monkeypatch.setattr("lakehouse.ops.seed.client", lambda *a, **k: fake)
    result = seed_bronze(4, settings=_settings())
    assert result["written"] == 4
    assert result["bucket"] == "bronze-test"
    assert result["sample_key"] is not None
    assert result["sample_key"].startswith("events/dt=")
    assert all(key.startswith("events/dt=") for (_, key) in fake.objects)
    assert all(body.startswith(b"{") for body in fake.objects.values())
