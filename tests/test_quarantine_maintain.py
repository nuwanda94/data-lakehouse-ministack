from __future__ import annotations

from datetime import UTC, datetime

from lakehouse.cli import main
from lakehouse.quarantine_maintain import (
    DATASET_ID,
    JOB,
    collect_snapshot,
    describe_quarantine_maintain,
    spec_snapshot,
)


def test_spec_snapshot_chains_expire_then_compact() -> None:
    as_of = datetime(2026, 9, 1, tzinfo=UTC)
    snap = spec_snapshot(as_of=as_of, retention_days=14, max_objects=8)
    assert snap["backend"] == "spec"
    assert snap["job"] == JOB
    assert snap["dataset"] == DATASET_ID
    assert snap["order"] == ["expire", "compact"]
    assert snap["expire_count"] == 1
    assert snap["compact_count"] == 1
    assert snap["apply"] is False
    assert snap["ok"] is True


def test_collect_and_describe() -> None:
    snap = collect_snapshot(as_of=datetime(2026, 9, 1, tzinfo=UTC))
    assert snap["backend"] in {"live", "spec"}
    assert snap["order"] == ["expire", "compact"]
    result = describe_quarantine_maintain(as_of=datetime(2026, 9, 1, tzinfo=UTC))
    assert result["dataset"] == DATASET_ID
    assert result["job"] == JOB
    assert result["retention_days"] >= 1
    assert result["max_objects"] >= 1
    assert (result["expire_count"] or 0) + (result["compact_count"] or 0) >= 1


def test_cli_quarantine_maintain(capsys: object) -> None:
    code = main(["quarantine-maintain"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"job": "quarantine.maintain"' in captured.out
    assert '"order"' in captured.out
    assert '"expire_count"' in captured.out
    assert '"compact_count"' in captured.out
    assert code == 0
