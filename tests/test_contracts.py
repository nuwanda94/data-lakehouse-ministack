"""Contract loader + zone key helpers stay aligned with CommerceEvent."""

from __future__ import annotations

from datetime import UTC, datetime

from lakehouse.contracts import load_contract
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.bronze import bronze_key
from lakehouse.pipeline.gold import gold_key
from lakehouse.pipeline.silver import quarantine_key, silver_key
from lakehouse.transforms.events import QuarantineRow


def test_contracts_exist_and_have_fields() -> None:
    for name in ("bronze", "silver", "gold", "quality", "pipeline_run"):
        doc = load_contract(name)
        assert isinstance(doc, dict)
        assert doc  # non-empty


def test_bronze_contract_fields_match_model() -> None:
    doc = load_contract("bronze")
    fields = {f["name"] for f in doc["fields"]}
    expected = {
        "event_id",
        "event_ts",
        "event_type",
        "user_id",
        "sku",
        "quantity",
        "amount_usd",
        "country",
    }
    assert expected.issubset(fields)


def test_zone_keys_stable() -> None:
    event = CommerceEvent(
        event_id="evt-1",
        event_type="purchase",
        event_ts=datetime(2024, 6, 15, 12, 0, tzinfo=UTC),
        user_id="u-1",
        sku="sku-9",
        quantity=2,
        amount_usd=9.99,
        country="US",
    )
    day = event.event_ts.date().isoformat()
    assert bronze_key(event) == f"events/dt={day}/{event.event_id}.json"
    assert (
        silver_key(event) == f"events/event_type={event.event_type}/dt={day}/{event.event_id}.json"
    )
    key = gold_key(metric="daily_metrics", day=day)
    assert "daily_metrics" in key and day in key
    q = quarantine_key(QuarantineRow(payload={"event_id": "evt-x"}, reason="missing_event_id"))
    assert q == "quarantine/reason=missing_event_id/evt-x.json"
