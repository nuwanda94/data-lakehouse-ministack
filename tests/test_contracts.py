"""Contract loader + zone key helpers stay aligned with CommerceEvent."""

from __future__ import annotations

from datetime import datetime, timezone

from lakehouse.contracts import load_contract
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.bronze import bronze_key
from lakehouse.pipeline.gold import gold_key
from lakehouse.pipeline.silver import quarantine_key, silver_key
from lakehouse.transforms.events import QuarantineRow


def test_contracts_exist_and_have_fields() -> None:
    for name in ("bronze", "silver", "gold", "quality", "pipeline_run"):
        doc = load_contract(name)
        assert "fields" in doc or "partition_keys" in doc or "required" in doc


def test_bronze_contract_fields_match_model() -> None:
    doc = load_contract("bronze")
    fields = {f["name"] for f in doc["fields"]}
    # CommerceEvent required + optional that land in bronze
    expected = {
        "event_id",
        "event_type",
        "event_ts",
        "customer_id",
        "sku",
        "quantity",
        "unit_price",
        "currency",
        "channel",
        "payload",
    }
    assert expected.issubset(fields)


def test_zone_keys_stable() -> None:
    event = CommerceEvent(
        event_id="evt-1",
        event_type="purchase",
        event_ts=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
        customer_id="c-1",
        sku="sku-9",
        quantity=2,
        unit_price=9.99,
        currency="USD",
        channel="web",
        payload={},
    )
    assert bronze_key(event) == f"events/dt={event.event_ts.date().isoformat()}/{event.event_id}.json"
    assert (
        silver_key(event)
        == f"events/dt={event.event_ts.date().isoformat()}/channel={event.channel}/{event.event_id}.json"
    )
    # gold_key signature is keyword-only metric/day
    assert gold_key(metric="daily_metrics", day=event.event_ts.date().isoformat()) == (
        f"metrics/metric=daily_metrics/dt={event.event_ts.date().isoformat()}/daily_metrics.json"
    )
    q = quarantine_key(QuarantineRow(payload={"event_id": "evt-x"}, reason="missing_event_id"))
    assert q == "quarantine/reason=missing_event_id/evt-x.json"
