"""ASL graph + local interpreter for the medallion Step Functions machine."""

from __future__ import annotations

import json
from pathlib import Path

from lakehouse.orchestration.sfn import STATE_ORDER, build_definition, run_sfn_local

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra" / "terraform" / "sfn.asl.json.tftpl"


def test_definition_has_required_states_and_start() -> None:
    definition = build_definition(
        ingest_arn="arn:aws:lambda:us-east-1:1:function:ingest",
        silver_arn="arn:aws:lambda:us-east-1:1:function:silver",
        quality_arn="arn:aws:lambda:us-east-1:1:function:quality",
        gold_arn="arn:aws:lambda:us-east-1:1:function:gold",
    )
    assert definition["StartAt"] == "IngestBronze"
    states = definition["States"]
    assert tuple(states) == STATE_ORDER
    assert states["IngestBronze"]["Next"] == "TransformSilver"
    assert states["TransformSilver"]["Next"] == "QualityGate"
    assert states["QualityGate"]["Next"] == "QualityChoice"
    assert states["QualityChoice"]["Default"] == "AggregateGold"
    assert states["QualityChoice"]["Choices"][0]["Next"] == "QualityFailed"
    assert states["AggregateGold"]["Next"] == "Succeeded"
    assert states["Succeeded"]["Type"] == "Succeed"
    assert states["QualityFailed"]["Type"] == "Fail"
    for name in ("IngestBronze", "TransformSilver", "QualityGate", "AggregateGold"):
        task = states[name]
        assert task["Type"] == "Task"
        assert task["Resource"] == "arn:aws:states:::lambda:invoke"
        assert task["Retry"]
        assert task["Catch"][0]["Next"] == "Failed"


def test_terraform_template_matches_python_graph() -> None:
    raw = TEMPLATE.read_text(encoding="utf-8")
    rendered = (
        raw.replace("${ingest_arn}", "I")
        .replace("${silver_arn}", "S")
        .replace("${quality_arn}", "Q")
        .replace("${gold_arn}", "G")
    )
    from_tf = json.loads(rendered)
    from_py = build_definition(ingest_arn="I", silver_arn="S", quality_arn="Q", gold_arn="G")
    assert from_tf["StartAt"] == from_py["StartAt"]
    assert set(from_tf["States"]) == set(from_py["States"])
    assert from_tf["States"]["IngestBronze"]["Next"] == from_py["States"]["IngestBronze"]["Next"]
    assert from_tf["States"]["QualityChoice"]["Default"] == "AggregateGold"


def test_local_interpreter_happy_path() -> None:
    calls: list[str] = []

    def _ok(name: str, extra: dict | None = None):
        def _fn(event):
            calls.append(name)
            payload = {"status": "succeeded", "run_id": "r1", "metrics": {}}
            if extra:
                payload.update(extra)
            return payload

        return _fn

    result = run_sfn_local(
        {"run_id": "r1"},
        ingest=_ok("ingest"),
        silver=_ok("silver"),
        quality=_ok("quality", {"passed": True}),
        gold=_ok("gold"),
    )
    assert result["terminal"] == "Succeeded"
    assert result["status"] == "succeeded"
    assert calls == ["ingest", "silver", "quality", "gold"]
    assert result["history"] == [
        "IngestBronze",
        "TransformSilver",
        "QualityGate",
        "QualityChoice",
        "AggregateGold",
        "Succeeded",
    ]


def test_local_interpreter_quality_fail_skips_gold() -> None:
    calls: list[str] = []

    def _ok(name: str):
        def _fn(event):
            calls.append(name)
            return {"status": "succeeded", "run_id": "r2"}

        return _fn

    def _gate(event):
        calls.append("quality")
        return {"status": "quality_failed", "passed": False, "error": "null_ids"}

    result = run_sfn_local(
        {},
        ingest=_ok("ingest"),
        silver=_ok("silver"),
        quality=_gate,
        gold=_ok("gold"),
    )
    assert result["terminal"] == "QualityFailed"
    assert result["status"] == "quality_failed"
    assert "gold" not in calls
    assert result["history"][-1] == "QualityFailed"


def test_local_interpreter_task_exception_goes_to_failed() -> None:
    def _boom(event):
        raise RuntimeError("ingest exploded")

    result = run_sfn_local(
        {},
        ingest=_boom,
        silver=lambda e: {"status": "succeeded"},
        quality=lambda e: {"status": "succeeded", "passed": True},
        gold=lambda e: {"status": "succeeded"},
    )
    assert result["terminal"] == "Failed"
    assert "exploded" in str(result["error"])
    assert result["history"] == ["IngestBronze", "Failed"]
