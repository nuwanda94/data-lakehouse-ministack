"""Failure-injection tests: Lambda crashes, poison SQS, schema drift.

These are hermetic (no MiniStack). They pin the behaviours Phase 2 promised:
the local SFN interpreter Catch path, Bronze ingest ignoring garbage
payloads, Silver quarantining drifted records, and the quality gate
blocking Gold when the contract is violated.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pytest

from lakehouse.config import Settings
from lakehouse.ingest.bronze_handler import ingest_bronze_event
from lakehouse.ingest.s3_events import extract_object_refs
from lakehouse.orchestration.sfn import run_sfn_local
from lakehouse.quality.gate import evaluate_quality
from lakehouse.silver.handler import transform_silver
from lakehouse.transforms.events import cleanse_to_silver, parse_bronze_record


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
        bronze_events_queue="bronze-events",
        bronze_events_queue_url="",
    )


def _ok_event(**overrides: Any) -> dict[str, Any]:
    base = {
        "event_id": "evt-1",
        "event_ts": "2026-01-02T12:00:00+00:00",
        "event_type": "purchase",
        "user_id": "user-001",
        "sku": "SKU-100",
        "quantity": 2,
        "amount_usd": 19.5,
        "country": "US",
    }
    base.update(overrides)
    return base


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        body = kwargs["Body"]
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = body
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = (kwargs["Bucket"], kwargs["Key"])
        if key not in self.objects:
            raise KeyError(key)
        return {"ContentLength": len(self.objects[key])}

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
        item = kwargs["Item"]
        run_id = item.get("run_id", {}).get("S")
        self.items = [i for i in self.items if i.get("run_id", {}).get("S") != run_id]
        self.items.append(item)
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        run_id = kwargs["Key"]["run_id"]["S"]
        for item in self.items:
            if item.get("run_id", {}).get("S") == run_id:
                return {"Item": item}
        return {}


# --- Lambda failures -------------------------------------------------------


def test_sfn_silver_exception_does_not_invoke_quality_or_gold() -> None:
    calls: list[str] = []

    def ingest(event: dict[str, Any]) -> dict[str, Any]:
        calls.append("ingest")
        return {"status": "succeeded", "run_id": "r-fail"}

    def silver(event: dict[str, Any]) -> dict[str, Any]:
        calls.append("silver")
        raise RuntimeError("lambda timed out")

    def quality(event: dict[str, Any]) -> dict[str, Any]:
        calls.append("quality")
        return {"status": "succeeded", "passed": True}

    def gold(event: dict[str, Any]) -> dict[str, Any]:
        calls.append("gold")
        return {"status": "succeeded"}

    result = run_sfn_local({}, ingest=ingest, silver=silver, quality=quality, gold=gold)
    assert result["terminal"] == "Failed"
    assert "timed out" in str(result["error"])
    assert calls == ["ingest", "silver"]
    assert result["history"] == ["IngestBronze", "TransformSilver", "Failed"]


def test_sfn_gold_exception_after_passing_gate() -> None:
    def gold(event: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("gold dynamodb unavailable")

    result = run_sfn_local(
        {},
        ingest=lambda e: {"status": "succeeded"},
        silver=lambda e: {"status": "succeeded"},
        quality=lambda e: {"status": "succeeded", "passed": True},
        gold=gold,
    )
    assert result["terminal"] == "Failed"
    assert "dynamodb unavailable" in str(result["error"])
    assert result["history"][-1] == "Failed"
    assert "AggregateGold" in result["history"]


def test_sfn_handler_status_failed_is_terminal() -> None:
    result = run_sfn_local(
        {},
        ingest=lambda e: {"status": "failed", "error": "all objects missing"},
        silver=lambda e: {"status": "succeeded"},
        quality=lambda e: {"status": "succeeded", "passed": True},
        gold=lambda e: {"status": "succeeded"},
    )
    assert result["terminal"] == "Failed"
    assert result["error"] == "all objects missing"
    assert "TransformSilver" not in result["history"]


# --- Poison messages -------------------------------------------------------


def test_poison_sqs_body_is_dropped_not_parsed_as_object() -> None:
    event = {
        "Records": [
            {"eventSource": "aws:sqs", "body": "this is not json {{{{"},
            {"eventSource": "aws:sqs", "body": "null"},
            {"eventSource": "aws:sqs", "body": "[]"},
            {"eventSource": "aws:sqs", "body": json.dumps({"hello": "world"})},
        ]
    }
    assert extract_object_refs(event) == []


def test_poison_sqs_mixed_with_valid_s3_keeps_only_valid() -> None:
    inner = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "events/dt=2026-01-02/ok.json"},
                },
            }
        ]
    }
    event = {
        "Records": [
            {"eventSource": "aws:sqs", "body": "{not-json"},
            {"eventSource": "aws:sqs", "body": json.dumps(inner)},
            {"eventSource": "aws:s3", "s3": {"bucket": {"name": "b"}}},
        ]
    }
    refs = extract_object_refs(event)
    assert [r.key for r in refs] == ["events/dt=2026-01-02/ok.json"]


def test_ingest_does_not_crash_on_poison_payload() -> None:
    result = ingest_bronze_event(
        {"Records": [{"eventSource": "aws:sqs", "body": "!!!"}]},
        settings=_settings(),
        s3=FakeS3(),
        ddb=FakeDDB(),
    )
    assert result["accepted"] == []
    assert result["missing"] == []
    assert result["status"] in {"succeeded", "pending", "failed"} or result["run_id"] is None


def test_ingest_marks_missing_object_as_failed_run() -> None:
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "events/dt=2026-01-02/ghost.json"},
                },
            }
        ]
    }
    result = ingest_bronze_event(event, settings=_settings(), s3=FakeS3(), ddb=FakeDDB())
    assert result["status"] == "failed"
    assert result["missing"]


# --- Schema drift ----------------------------------------------------------


@pytest.mark.parametrize(
    "payload,reason",
    [
        ({}, "empty_record"),
        ({"event_id": "", "event_type": "purchase"}, "missing_event_id"),
        (
            {
                **_ok_event(event_type="subscription"),
            },
            "unknown_event_type",
        ),
        ({**_ok_event(), "quantity": "two"}, "non_numeric_measures"),
        ({**_ok_event(), "amount_usd": "free"}, "non_numeric_measures"),
        ({**_ok_event(), "event_ts": "not-a-timestamp"}, "schema_invalid"),
        ({**_ok_event(), "quantity": -3}, "non_positive_quantity"),
    ],
)
def test_schema_drift_is_quarantined_with_stable_reason(payload: dict[str, Any], reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        parse_bronze_record(payload)
    batch = cleanse_to_silver([payload])
    assert batch.valid == []
    assert [row.reason for row in batch.quarantined] == [reason]


def test_unknown_columns_are_ignored_when_required_fields_hold() -> None:
    drifted = _ok_event(campaign="summer-sale", device="ios", nested={"ok": True})
    parsed = parse_bronze_record(drifted)
    assert parsed.event_id == "evt-1"
    dumped = parsed.model_dump()
    assert "campaign" not in dumped
    assert "device" not in dumped


def test_silver_handler_quarantines_drifted_bronze_json() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(
        Bucket="b",
        Key="events/dt=2026-01-02/ok.json",
        Body=json.dumps(_ok_event()),
    )
    s3.put_object(
        Bucket="b",
        Key="events/dt=2026-01-02/drift.json",
        Body=json.dumps(_ok_event(event_id="evt-drift", event_type="checkout_v2")),
    )
    s3.put_object(
        Bucket="b",
        Key="events/dt=2026-01-02/garbage.json",
        Body=b"not-json at all",
    )
    result = transform_silver(None, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "succeeded"
    assert result["valid"] == 1
    assert result["quarantined"] == 2
    assert len(result["quarantine_written"]) == 2
    assert any("checkout_v2" not in k for k in result["silver_written"])


def test_quality_gate_fails_on_contract_drift() -> None:
    decision = evaluate_quality(
        [
            _ok_event(),
            _ok_event(event_id="evt-2", event_type="impression"),
            _ok_event(event_id="evt-3", event_ts="yesterday"),
        ]
    )
    assert not decision.passed
    assert decision.action == "fail"
    names = {r.check_name: r for r in decision.results}
    assert names["known_event_type"].passed is False
    assert names["schema_valid"].passed is False
    assert decision.rows_failed == 2
