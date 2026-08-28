from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from lakehouse.config import Settings
from lakehouse.models import CommerceEvent
from lakehouse.pipeline.quality import run_quality_checks
from lakehouse.quality.gate import evaluate_quality
from lakehouse.quality.handler import run_quality_gate


def _event(**overrides: Any) -> dict[str, Any]:
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


def test_clean_batch_passes() -> None:
    decision = evaluate_quality([_event(), _event(event_id="evt-2")])
    assert decision.passed
    assert decision.action == "pass"
    assert decision.rows_failed == 0
    assert all(r.passed for r in decision.results)


def test_empty_batch_passes() -> None:
    decision = evaluate_quality([])
    assert decision.passed
    assert decision.rows_scanned == 0


def test_invalid_rows_fail_named_checks() -> None:
    decision = evaluate_quality(
        [
            _event(event_id=""),
            _event(event_id="evt-2", event_type="click"),
            _event(event_id="evt-3", quantity=0, amount_usd=-1),
            _event(event_id="evt-4", user_id="", sku=""),
        ]
    )
    assert not decision.passed
    assert decision.action == "fail"
    names = {r.check_name: r for r in decision.results}
    assert not names["event_id_present"].passed
    assert not names["known_event_type"].passed
    assert not names["quantity_and_amount_sane"].passed
    assert not names["required_dimensions"].passed
    assert decision.rows_failed == 4


def test_quarantine_action_when_configured() -> None:
    decision = evaluate_quality([_event(event_id="")], on_fail="quarantine")
    assert not decision.passed
    assert decision.action == "quarantine"
    assert "event_id_present" in decision.failed_rows[0].reasons


def test_max_fail_ratio_allows_small_drift() -> None:
    records = [_event(event_id=f"evt-{i}") for i in range(9)]
    records.append(_event(event_id="bad", event_type="nope"))
    decision = evaluate_quality(records, max_fail_ratio=0.2)
    assert decision.passed
    assert decision.rows_failed == 1


def test_compat_wrapper_on_commerce_events() -> None:
    events = [CommerceEvent.model_validate(_event())]
    results = run_quality_checks(events)
    assert all(r.passed for r in results)


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


def test_handler_passes_clean_silver_and_writes_report() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(
        Bucket="s",
        Key="events/event_type=purchase/dt=2026-01-02/evt-1.json",
        Body=json.dumps(_event()),
    )
    result = run_quality_gate(None, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "succeeded"
    assert result["passed"] is True
    assert result["rows_scanned"] == 1
    assert result["report_key"].startswith("quality/")
    assert ("s", result["report_key"]) in s3.objects
    assert ddb.items[0]["zone"]["S"] == "silver"
    assert ddb.items[0]["status"]["S"] == "succeeded"


def test_handler_fails_run_on_bad_rows() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(
        Bucket="s",
        Key="events/event_type=purchase/dt=2026-01-02/bad.json",
        Body=json.dumps(_event(event_id="", event_type="nope")),
    )
    result = run_quality_gate(None, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "quality_failed"
    assert result["passed"] is False
    assert result["action"] == "fail"
    assert result["quarantine_written"] == []
    assert ddb.items[0]["status"]["S"] == "quality_failed"


def test_handler_quarantines_on_fail_mode() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(
        Bucket="s",
        Key="events/event_type=purchase/dt=2026-01-02/bad.json",
        Body=json.dumps(_event(quantity=0)),
    )
    result = run_quality_gate(
        None, settings=_settings(), s3=s3, ddb=ddb, on_fail="quarantine"
    )
    assert result["status"] == "succeeded"
    assert result["action"] == "quarantine"
    assert result["quarantine_written"]
    assert any(key.startswith("quarantine/") for key in result["quarantine_written"])


def test_handler_skips_non_events_prefix() -> None:
    result = run_quality_gate(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "s3": {
                        "bucket": {"name": "s"},
                        "object": {"key": "quarantine/reason=x/bad.json"},
                    },
                }
            ]
        },
        settings=_settings(),
        s3=FakeS3(),
        ddb=FakeDDB(),
    )
    assert result["skipped"] == ["quarantine/reason=x/bad.json"]
    assert result["passed"] is True
