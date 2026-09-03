from __future__ import annotations

from lakehouse.gold_quarantine_compact import (
    DATASET_ID,
    DEFAULT_MAX_OBJECTS,
    classify_partition,
    collect_snapshot,
    compact_key,
    describe_gold_quarantine_compact,
    merge_quarantine_payloads,
    plan_compact,
    resolve_max_objects,
    spec_snapshot,
)


def test_classify_keep_and_compact() -> None:
    keep = classify_partition(
        reason="unreadable_silver",
        metric="purchase",
        dt="2026-09-01",
        objects=1,
        max_objects=2,
    )
    compact = classify_partition(
        reason="unknown_event_type",
        metric="page_view",
        dt="2026-08-25",
        objects=4,
        max_objects=2,
    )
    assert keep["compact"] is False
    assert keep["action"] == "keep"
    assert compact["compact"] is True
    assert compact["action"] == "compact"
    assert compact["target"] == compact_key(
        reason="unknown_event_type",
        metric="page_view",
        dt="2026-08-25",
    )


def test_plan_counts() -> None:
    plan = plan_compact(
        [
            {
                "reason": "unreadable_silver",
                "metric": "purchase",
                "dt": "2026-09-01",
                "objects": 1,
            },
            {
                "reason": "unknown_event_type",
                "metric": "page_view",
                "dt": "2026-08-25",
                "objects": 5,
            },
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
    assert snap["compact"][0]["reason"] == "unknown_event_type"
    assert snap["compact"][0]["objects"] == 4
    assert snap["apply"] is False


def test_collect_and_describe() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    result = describe_gold_quarantine_compact()
    assert result["dataset"] == DATASET_ID
    assert result["max_objects"] == DEFAULT_MAX_OBJECTS or result["max_objects"] >= 1
    assert result["keep_count"] + result["compact_count"] >= 1


def test_resolve_env_override(monkeypatch: object) -> None:
    monkeypatch.setenv("LAKEHOUSE_GOLD_QUARANTINE_COMPACT_MAX_OBJECTS", "5")  # type: ignore[attr-defined]
    assert resolve_max_objects() == 5
    assert resolve_max_objects(3) == 3


def test_merge_quarantine_payloads() -> None:
    merged = merge_quarantine_payloads(
        [
            {
                "reason": "unknown_event_type",
                "zone": "gold",
                "payload": {"event_type": "page_view", "dt": "2026-08-25", "events": 0},
            },
            {
                "reason": "unknown_event_type",
                "zone": "gold",
                "payload": {"event_type": "page_view", "dt": "2026-08-25", "events": -1},
            },
        ]
    )
    assert merged["record_count"] == 2
    assert merged["compacted_from"] == 2
    assert merged["reason"] == "unknown_event_type"
    assert merged["metric"] == "page_view"
    assert merged["dt"] == "2026-08-25"
    assert merged["zone"] == "gold"


def test_boundary_equals_max_is_keep() -> None:
    row = classify_partition(
        reason="non_positive_events",
        metric="purchase",
        dt="2026-09-01",
        objects=2,
        max_objects=2,
    )
    assert row["compact"] is False
