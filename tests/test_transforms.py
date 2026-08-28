"""Unit tests for bronze→silver cleanse and gold aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lakehouse.models import CommerceEvent
from lakehouse.pipeline.quality import run_quality_checks
from lakehouse.pipeline.silver import silver_key
from lakehouse.seed.generate import generate_events
from lakehouse.transforms.events import (
    aggregate_gold,
    cleanse_to_silver,
    is_late,
    parse_bronze_record,
)


def _event(**overrides: object) -> CommerceEvent:
    base = dict(
        event_id="evt-ok",
        event_ts=datetime(2026, 1, 10, 12, tzinfo=UTC),
        event_type="purchase",
        user_id="user-001",
        sku="SKU-100",
        quantity=2,
        amount_usd=12.5,
        country="US",
    )
    base.update(overrides)
    return CommerceEvent.model_validate(base)


def test_cleanse_empty_batch() -> None:
    batch = cleanse_to_silver([])
    assert batch.empty
    assert batch.valid == []
    assert batch.quarantined == []
    assert batch.late == []
    assert aggregate_gold([]) == []


def test_cleanse_all_invalid_rows() -> None:
    records = [
        {},
        {"event_id": "", "event_type": "purchase", "quantity": 1, "amount_usd": 1},
        {
            "event_id": "evt-bad-type",
            "event_ts": "2026-01-10T00:00:00+00:00",
            "event_type": "explode",
            "user_id": "u",
            "sku": "SKU-100",
            "quantity": 1,
            "amount_usd": 1.0,
        },
        {
            "event_id": "evt-qty",
            "event_ts": "2026-01-10T00:00:00+00:00",
            "event_type": "purchase",
            "user_id": "u",
            "sku": "SKU-100",
            "quantity": 0,
            "amount_usd": 1.0,
        },
        {
            "event_id": "evt-amt",
            "event_ts": "2026-01-10T00:00:00+00:00",
            "event_type": "refund",
            "user_id": "u",
            "sku": "SKU-100",
            "quantity": 1,
            "amount_usd": -9.99,
        },
    ]
    batch = cleanse_to_silver(records)
    assert batch.valid == []
    assert batch.late == []
    assert len(batch.quarantined) == len(records)
    reasons = {row.reason for row in batch.quarantined}
    assert "empty_record" in reasons
    assert "missing_event_id" in reasons
    assert "unknown_event_type" in reasons
    assert "non_positive_quantity" in reasons
    assert "negative_amount" in reasons


def test_parse_bronze_record_happy_path() -> None:
    raw = generate_events(1, seed=4)[0].model_dump(mode="json")
    parsed = parse_bronze_record(raw)
    assert parsed.event_id == raw["event_id"]


def test_late_arriving_events_are_tagged_not_quarantined() -> None:
    watermark = datetime(2026, 1, 10, tzinfo=UTC)
    lookback = timedelta(days=2)
    on_time = _event(
        event_id="evt-on-time",
        event_ts=datetime(2026, 1, 9, 12, tzinfo=UTC),
    )
    late = _event(
        event_id="evt-late",
        event_ts=datetime(2026, 1, 7, 11, tzinfo=UTC),
    )
    just_inside = _event(
        event_id="evt-edge",
        event_ts=datetime(2026, 1, 8, tzinfo=UTC),
    )
    assert is_late(late, watermark=watermark, lookback=lookback)
    assert not is_late(on_time, watermark=watermark, lookback=lookback)
    assert not is_late(just_inside, watermark=watermark, lookback=lookback)

    batch = cleanse_to_silver(
        [on_time, late, just_inside],
        watermark=watermark,
        lookback=lookback,
    )
    assert [e.event_id for e in batch.valid] == ["evt-on-time", "evt-edge"]
    assert [e.event_id for e in batch.late] == ["evt-late"]
    assert batch.quarantined == []


def test_mixed_batch_splits_valid_late_and_quarantine() -> None:
    watermark = datetime(2026, 6, 1, tzinfo=UTC)
    good = _event(event_id="evt-good", event_ts=datetime(2026, 5, 31, tzinfo=UTC))
    late = _event(event_id="evt-old", event_ts=datetime(2026, 1, 1, tzinfo=UTC))
    bad = {
        "event_id": "evt-x",
        "event_ts": "2026-05-31T00:00:00+00:00",
        "event_type": "nope",
        "user_id": "u",
        "sku": "SKU-100",
        "quantity": 1,
        "amount_usd": 1.0,
    }
    batch = cleanse_to_silver(
        [good, late, bad],
        watermark=watermark,
        lookback=timedelta(days=7),
    )
    assert [e.event_id for e in batch.valid] == ["evt-good"]
    assert [e.event_id for e in batch.late] == ["evt-old"]
    assert [row.reason for row in batch.quarantined] == ["unknown_event_type"]


def test_aggregate_gold_groups_by_day_and_type() -> None:
    events = [
        _event(
            event_id="a",
            event_type="purchase",
            event_ts=datetime(2026, 1, 1, 1, tzinfo=UTC),
            amount_usd=10.0,
        ),
        _event(
            event_id="b",
            event_type="purchase",
            event_ts=datetime(2026, 1, 1, 2, tzinfo=UTC),
            amount_usd=2.25,
        ),
        _event(
            event_id="c",
            event_type="refund",
            event_ts=datetime(2026, 1, 1, 3, tzinfo=UTC),
            amount_usd=1.0,
        ),
        _event(
            event_id="d",
            event_type="purchase",
            event_ts=datetime(2026, 1, 2, tzinfo=UTC),
            amount_usd=5.0,
        ),
    ]
    gold = aggregate_gold(events)
    assert gold == [
        {"dt": "2026-01-01", "event_type": "purchase", "events": 2, "amount_usd": 12.25},
        {"dt": "2026-01-01", "event_type": "refund", "events": 1, "amount_usd": 1.0},
        {"dt": "2026-01-02", "event_type": "purchase", "events": 1, "amount_usd": 5.0},
    ]


def test_quality_gate_empty_and_all_invalid() -> None:
    empty = run_quality_checks([])
    assert empty
    assert all(r.passed and r.rows_scanned == 0 for r in empty)

    zero_qty = _event(event_id="z", quantity=0)
    unknown = _event(event_id="u", event_type="page_view").model_copy(
        update={"event_type": "mystery"}
    )
    results = {r.check_name: r for r in run_quality_checks([zero_qty, unknown])}
    assert results["quantity_and_amount_sane"].passed is False
    assert results["quantity_and_amount_sane"].rows_failed == 1
    assert results["known_event_type"].passed is False
    assert results["known_event_type"].rows_failed == 1


def test_silver_key_includes_type_and_day() -> None:
    event = _event(event_type="add_to_cart", event_ts=datetime(2026, 3, 4, tzinfo=UTC))
    key = silver_key(event)
    assert key == f"events/event_type=add_to_cart/dt=2026-03-04/{event.event_id}.json"
