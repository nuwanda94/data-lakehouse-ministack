from __future__ import annotations

from lakehouse.cli import main
from lakehouse.silver_compact import (
    DATASET_ID,
    DEFAULT_MAX_OBJECTS,
    classify_partition,
    collect_snapshot,
    compact_key,
    describe_silver_compact,
    merge_event_payloads,
    plan_compact,
    resolve_max_objects,
    spec_snapshot,
)


def test_classify_keep_and_compact() -> None:
    keep = classify_partition(
        event_type="purchase",
        dt="2026-09-01",
        objects=1,
        max_objects=8,
    )
    compact = classify_partition(
        event_type="page_view",
        dt="2026-08-25",
        objects=10,
        max_objects=8,
    )
    assert keep["compact"] is False
    assert keep["action"] == "keep"
    assert compact["compact"] is True
    assert compact["action"] == "compact"
    assert compact["target"] == compact_key(event_type="page_view", dt="2026-08-25")


def test_plan_counts() -> None:
    plan = plan_compact(
        [
            {"event_type": "purchase", "dt": "2026-09-01", "objects": 1},
            {"event_type": "page_view", "dt": "2026-08-25", "objects": 12},
        ],
        max_objects=8,
    )
    assert plan["keep_count"] == 1
    assert plan["compact_count"] == 1
    assert plan["dataset"] == DATASET_ID
    assert plan["max_objects"] == 8


def test_spec_snapshot_includes_fragmented_fixture() -> None:
    snap = spec_snapshot(max_objects=8)
    assert snap["backend"] == "spec"
    assert snap["keep_count"] == 1
    assert snap["compact_count"] == 1
    assert snap["compact"][0]["dt"] == "2026-08-25"
    assert snap["compact"][0]["event_type"] == "page_view"
    assert snap["compact"][0]["objects"] == 10
    assert snap["apply"] is False


def test_collect_and_describe() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    result = describe_silver_compact()
    assert result["dataset"] == DATASET_ID
    assert result["max_objects"] == DEFAULT_MAX_OBJECTS or result["max_objects"] >= 1
    assert result["keep_count"] + result["compact_count"] >= 1


def test_resolve_env_override(monkeypatch: object) -> None:
    monkeypatch.setenv("LAKEHOUSE_SILVER_COMPACT_MAX_OBJECTS", "5")  # type: ignore[attr-defined]
    assert resolve_max_objects() == 5
    assert resolve_max_objects(3) == 3


def test_merge_event_payloads() -> None:
    merged = merge_event_payloads(
        [
            {"event_id": "a", "dt": "2026-09-01", "event_type": "page_view"},
            {"event_id": "b", "dt": "2026-09-01", "event_type": "page_view"},
            {"dt": "2026-09-01", "event_type": "page_view", "events": [{"event_id": "c"}]},
        ]
    )
    assert merged["record_count"] == 3
    assert merged["compacted_from"] == 3
    assert merged["dt"] == "2026-09-01"
    assert merged["event_type"] == "page_view"
    assert [row["event_id"] for row in merged["events"]] == ["a", "b", "c"]


def test_cli_silver_compact(capsys: object) -> None:
    code = main(["silver-compact"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"dataset": "silver.cleaned_events"' in captured.out
    assert '"max_objects"' in captured.out
    assert code == 0


def test_boundary_equals_max_is_keep() -> None:
    row = classify_partition(
        event_type="purchase",
        dt="2026-09-01",
        objects=8,
        max_objects=8,
    )
    assert row["compact"] is False
