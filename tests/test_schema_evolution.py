"""Schema evolution + producer contract tests."""

from __future__ import annotations

import copy

from lakehouse.cli import main
from lakehouse.contract_check import (
    check_all,
    compare_contracts,
    errors_only,
    report_issues,
    validate_contract_document,
    validate_payload,
)
from lakehouse.contracts import load_contract
from lakehouse.models import CommerceEvent
from lakehouse.seed.generate import generate_events


def test_checked_in_contracts_are_well_formed() -> None:
    issues = check_all()
    assert errors_only(issues) == [], report_issues(issues)


def test_seed_payloads_match_bronze_contract() -> None:
    spec = load_contract("bronze")
    for event in generate_events(8, seed=3):
        found = validate_payload(event.model_dump(), spec, contract="bronze")
        assert errors_only(found) == []


def test_missing_required_field_is_an_error() -> None:
    spec = load_contract("bronze")
    payload = generate_events(1, seed=1)[0].model_dump()
    del payload["event_id"]
    codes = {item.code for item in validate_payload(payload, spec, contract="bronze")}
    assert "missing_required" in codes


def test_unknown_event_type_is_an_error() -> None:
    spec = load_contract("bronze")
    payload = generate_events(1, seed=1)[0].model_dump()
    payload["event_type"] = "chargeback"
    codes = {item.code for item in validate_payload(payload, spec, contract="bronze")}
    assert "enum_mismatch" in codes


def test_additive_optional_field_is_compatible() -> None:
    old = load_contract("bronze")
    new = copy.deepcopy(old)
    new["fields"].append({"name": "channel", "type": "string", "required": False})
    diff = compare_contracts(old, new, name="bronze")
    assert diff.compatible
    assert any("channel" in item for item in diff.additive)


def test_removing_required_field_is_breaking() -> None:
    old = load_contract("bronze")
    new = copy.deepcopy(old)
    new["fields"] = [item for item in new["fields"] if item["name"] != "sku"]
    diff = compare_contracts(old, new, name="bronze")
    assert not diff.compatible


def test_adding_required_field_is_breaking() -> None:
    old = load_contract("gold")
    new = copy.deepcopy(old)
    new["fields"].append({"name": "currency", "type": "string", "required": True})
    diff = compare_contracts(old, new, name="gold")
    assert not diff.compatible


def test_enum_value_removal_is_breaking() -> None:
    old = load_contract("silver")
    new = copy.deepcopy(old)
    for item in new["fields"]:
        if item["name"] == "event_type":
            item["enum"] = [v for v in item["enum"] if v != "refund"]
    diff = compare_contracts(old, new, name="silver")
    assert not diff.compatible


def test_enum_value_addition_is_additive() -> None:
    old = load_contract("silver")
    new = copy.deepcopy(old)
    for item in new["fields"]:
        if item["name"] == "event_type":
            item["enum"] = [*item["enum"], "subscription"]
    diff = compare_contracts(old, new, name="silver")
    assert diff.compatible


def test_type_narrowing_is_breaking() -> None:
    old = {"name": "x", "fields": [{"name": "n", "type": "number", "required": True}]}
    new = {"name": "x", "fields": [{"name": "n", "type": "integer", "required": True}]}
    assert not compare_contracts(old, new, name="x").compatible


def test_type_widening_is_additive() -> None:
    old = {"name": "x", "fields": [{"name": "n", "type": "integer", "required": True}]}
    new = {"name": "x", "fields": [{"name": "n", "type": "number", "required": True}]}
    assert compare_contracts(old, new, name="x").compatible


def test_partition_key_change_is_breaking() -> None:
    old = load_contract("silver")
    new = copy.deepcopy(old)
    new["partitioning"]["hive"] = ["dt"]
    assert not compare_contracts(old, new, name="silver").compatible


def test_quality_check_removal_is_breaking() -> None:
    old = load_contract("quality")
    new = copy.deepcopy(old)
    new["checks"] = new["checks"][1:]
    assert not compare_contracts(old, new, name="quality").compatible


def test_malformed_document_is_rejected() -> None:
    issues = validate_contract_document(
        "bronze", {"name": "x", "fields": [{"name": "a", "type": "not-a-type"}]}
    )
    assert any(item.code == "unknown_type" for item in issues)


def test_commerce_event_round_trip_stays_on_contract() -> None:
    spec = load_contract("bronze")
    event = CommerceEvent.model_validate(generate_events(1, seed=9)[0].model_dump())
    assert errors_only(validate_payload(event.model_dump(), spec, contract="bronze")) == []


def test_cli_contracts_ok(capsys: object) -> None:
    assert main(["contracts"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"ok": true' in captured.out
