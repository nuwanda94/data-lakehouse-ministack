from __future__ import annotations

from lakehouse.cli import main
from lakehouse.quarantine_compact import (
    DATASET_ID,
    classify_prefix,
    collect_snapshot,
    describe_quarantine_compact,
    plan_compact,
    spec_snapshot,
)


def test_classify_keep_and_compact() -> None:
    keep = classify_prefix(reason="schema", objects=1, max_objects=8)
    compact = classify_prefix(reason="poison", objects=10, max_objects=8)
    assert keep["action"] == "keep"
    assert keep["compact"] is False
    assert compact["action"] == "compact"
    assert compact["compact"] is True
    assert compact["target"].endswith("part-000.json")


def test_plan_and_spec_snapshot() -> None:
    plan = plan_compact(
        [
            {"reason": "schema", "objects": 1},
            {"reason": "poison", "objects": 12},
        ],
        max_objects=8,
    )
    assert plan["dataset"] == DATASET_ID
    assert plan["keep_count"] == 1
    assert plan["compact_count"] == 1
    snap = spec_snapshot(max_objects=8)
    assert snap["backend"] == "spec"
    assert snap["compact_count"] == 1
    assert snap["apply"] is False


def test_collect_and_describe() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    result = describe_quarantine_compact()
    assert result["dataset"] == DATASET_ID
    assert result["max_objects"] >= 1
    assert (result["keep_count"] or 0) + (result["compact_count"] or 0) >= 1


def test_cli_quarantine_compact(capsys: object) -> None:
    code = main(["quarantine-compact"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"dataset": "silver.quarantine"' in captured.out
    assert '"compact_count"' in captured.out
    assert code == 0
