from __future__ import annotations

from typing import Any

from lakehouse.models import QualityResult
from lakehouse.pipeline.runs import (
    complete_run,
    get_run,
    item_to_run,
    list_runs,
    new_run,
    persist_run,
    resolve_run_id,
    run_to_item,
)


class FakeDDB:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        item = kwargs["Item"]
        self.store[item["run_id"]["S"]] = item
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        run_id = kwargs["Key"]["run_id"]["S"]
        item = self.store.get(run_id)
        return {"Item": item} if item else {}

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        return {"Items": list(self.store.values())}


def test_resolve_run_id_prefers_event_then_env(monkeypatch: Any) -> None:
    monkeypatch.delenv("LAKEHOUSE_RUN_ID", raising=False)
    monkeypatch.delenv("PIPELINE_RUN_ID", raising=False)
    assert resolve_run_id({"run_id": "evt-123"}) == "evt-123"
    monkeypatch.setenv("LAKEHOUSE_RUN_ID", "env-9")
    assert resolve_run_id(None) == "env-9"
    assert resolve_run_id({"Records": []}) == "env-9"
    assert resolve_run_id(None, explicit="given") == "given"
    monkeypatch.delenv("LAKEHOUSE_RUN_ID", raising=False)
    generated = resolve_run_id({"Records": []})
    assert generated
    assert len(generated) >= 8


def test_persist_roundtrip_includes_metrics_status_and_error() -> None:
    ddb = FakeDDB()
    run = new_run(zone="silver", status="running", step="quality", run_id="run-abc")
    complete_run(
        run,
        status="quality_failed",
        error="quality gate failed: not_null_event_id",
        objects=["events/dt=2026-01-02/a.json"],
        metrics={"rows_scanned": 10, "rows_failed": 2},
        quality=[
            QualityResult(
                check_name="not_null_event_id",
                passed=False,
                rows_scanned=10,
                rows_failed=2,
                detail="2 empty ids",
            )
        ],
    )
    persist_run(ddb, "runs", run)

    item = ddb.store["run-abc"]
    assert item["status"]["S"] == "quality_failed"
    assert item["step"]["S"] == "quality"
    assert item["error"]["S"].startswith("quality gate failed")
    assert item["rows_scanned"]["N"] == "10"
    assert item["object_count"]["N"] == "1"
    assert "finished_at" in item

    loaded = get_run(ddb, "runs", "run-abc")
    assert loaded is not None
    assert loaded.run_id == "run-abc"
    assert loaded.status == "quality_failed"
    assert loaded.metrics["rows_failed"] == 2
    assert loaded.objects == ["events/dt=2026-01-02/a.json"]
    assert loaded.quality[0].check_name == "not_null_event_id"

    listed = list_runs(ddb, "runs")
    assert [r.run_id for r in listed] == ["run-abc"]


def test_item_to_run_recovers_flattened_metrics_without_metrics_blob() -> None:
    item = run_to_item(
        complete_run(
            new_run(zone="gold", status="running", step="gold", run_id="g1"),
            status="succeeded",
            metrics={"gold_written": 3},
        )
    )
    item.pop("metrics")
    decoded = item_to_run(item)
    assert decoded.metrics["gold_written"] == 3
    assert decoded.zone == "gold"
