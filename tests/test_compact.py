from __future__ import annotations

from lakehouse.cli import main
from lakehouse.compact import (
    DATASET_ID,
    DEFAULT_MAX_OBJECTS,
    classify_partition,
    collect_snapshot,
    compact_key,
    describe_compact,
    merge_metric_payloads,
    plan_compact,
    resolve_max_objects,
    spec_snapshot,
)


def test_classify_keep_and_compact() -> None:
    keep = classify_partition(
        metric="purchase",
        dt="2026-09-01",
        objects=1,
        max_objects=2,
    )
    compact = classify_partition(
        metric="page_view",
        dt="2026-08-25",
        objects=4,
        max_objects=2,
    )
    assert keep["compact"] is False
    assert keep["action"] == "keep"
    assert compact["compact"] is True
    assert compact["action"] == "compact"
    assert compact["target"] == compact_key(metric="page_view", dt="2026-08-25")


def test_plan_counts() -> None:
    plan = plan_compact(
        [
            {"metric": "purchase", "dt": "2026-09-01", "objects": 1},
            {"metric": "page_view", "dt": "2026-08-25", "objects": 5},
        ],
        max_objects=2,
    )
    assert plan["keep_count"] == 1
    assert plan["compact_count"] == 1
    assert plan["dataset"] == DATASET_ID
    assert plan["max_objects"] == 2


def test_spec_snapshot_includes_fragmented_fixture() -> None:
    snap = spec_snapshot(max_objects=2)
    assert snap["backend"] == "spec"
    assert snap["keep_count"] == 1
    assert snap["compact_count"] == 1
    assert snap["compact"][0]["metric"] == "page_view"
    assert snap["compact"][0]["objects"] == 4
    assert snap["apply"] is False


def test_collect_and_describe() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    result = describe_compact()
    assert result["dataset"] == DATASET_ID
    assert result["max_objects"] == DEFAULT_MAX_OBJECTS or result["max_objects"] >= 1
    assert result["keep_count"] + result["compact_count"] >= 1


def test_resolve_env_override(monkeypatch: object) -> None:
    monkeypatch.setenv("LAKEHOUSE_GOLD_COMPACT_MAX_OBJECTS", "5")  # type: ignore[attr-defined]
    assert resolve_max_objects() == 5
    assert resolve_max_objects(3) == 3


def test_merge_metric_payloads() -> None:
    merged = merge_metric_payloads(
        [
            {"event_type": "purchase", "dt": "2026-09-01", "events": 2, "amount_usd": 10.5},
            {"event_type": "purchase", "dt": "2026-09-01", "events": 3, "amount_usd": 4.5},
        ]
    )
    assert merged["events"] == 5
    assert merged["amount_usd"] == 15.0
    assert merged["compacted_from"] == 2


def test_cli_compact(capsys: object) -> None:
    code = main(["compact"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"dataset": "gold.daily_metrics"' in captured.out
    assert '"max_objects"' in captured.out
    assert code == 0


def test_boundary_equals_max_is_keep() -> None:
    row = classify_partition(
        metric="purchase",
        dt="2026-09-01",
        objects=2,
        max_objects=2,
    )
    assert row["compact"] is False
