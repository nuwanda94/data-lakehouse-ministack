"""Keep configs/contracts/ aligned with CommerceEvent and zone helpers."""

from __future__ import annotations

from lakehouse.contracts import CONTRACT_NAMES, contract_field_names, load_all_contracts, load_contract
from lakehouse.models import CommerceEvent, PipelineRun
from lakehouse.pipeline.bronze import bronze_key
from lakehouse.pipeline.gold import gold_key
from lakehouse.pipeline.silver import quarantine_key, silver_key
from lakehouse.quality.gate import evaluate_quality
from lakehouse.seed.generate import generate_events
from lakehouse.transforms.events import QuarantineRow


COMMERCE_FIELDS = set(CommerceEvent.model_fields)


def test_all_contract_files_load() -> None:
    loaded = load_all_contracts()
    assert set(loaded) == set(CONTRACT_NAMES)
    for name, spec in loaded.items():
        assert spec, name


def test_bronze_and_silver_cover_commerce_event() -> None:
    bronze = set(contract_field_names("bronze"))
    silver = set(contract_field_names("silver"))
    assert COMMERCE_FIELDS <= bronze
    assert COMMERCE_FIELDS <= silver
    assert "_late" in silver
    assert "_late" not in bronze


def test_gold_fields_match_aggregate_shape() -> None:
    assert contract_field_names("gold") == ["dt", "event_type", "events", "amount_usd"]
    gold = load_contract("gold")
    assert gold["dynamodb"]["pk"] == "metric_day"


def test_quality_check_names_match_gate() -> None:
    names = [c["name"] for c in load_contract("quality")["checks"]]
    decision = evaluate_quality([])
    assert [r.check_name for r in decision.results] == names


def test_pipeline_run_contract_covers_model() -> None:
    contracted = set(contract_field_names("pipeline_run"))
    assert {"run_id", "status", "started_at", "zone", "step"} <= contracted
    assert set(PipelineRun.model_fields) - {"metrics"} <= contracted | {
        "quality",
        "objects",
        "error",
        "parent_run_id",
        "finished_at",
    }


def test_partition_key_templates_match_helpers() -> None:
    event = generate_events(1)[0]
    assert bronze_key(event) == f"events/dt={event.event_ts.date().isoformat()}/{event.event_id}.json"
    assert silver_key(event) == (
        f"events/event_type={event.event_type}/dt={event.event_ts.date().isoformat()}/{event.event_id}.json"
    )
    assert gold_key(metric="purchase", day="2026-01-01") == "metrics/metric=purchase/dt=2026-01-01/part-000.json"
    q = quarantine_key(QuarantineRow(payload={"event_id": "evt-x"}, reason="missing_event_id"))
    assert q == "quarantine/reason=missing_event_id/evt-x.json"
