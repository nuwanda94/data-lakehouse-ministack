from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lakehouse.cli import main
from lakehouse.quarantine_retention import (
    DATASET_ID,
    DEFAULT_RETENTION_DAYS,
    classify_object,
    collect_snapshot,
    describe_quarantine_retention,
    parse_quarantine_key,
    plan_retention,
    resolve_retention_days,
    spec_snapshot,
)


def test_parse_quarantine_key() -> None:
    meta = parse_quarantine_key("quarantine/reason=schema+missing/evt-9.json")
    assert meta["reason"] == "schema+missing"
    assert meta["event_id"] == "evt-9"


def test_classify_keep_and_expire() -> None:
    as_of = datetime(2026, 9, 1, tzinfo=UTC)
    keep = classify_object(
        written_at="2026-08-28T00:00:00+00:00",
        as_of=as_of,
        retention_days=14,
        reason="schema",
        event_id="evt-keep",
    )
    expire = classify_object(
        written_at="2026-07-01T00:00:00+00:00",
        as_of=as_of,
        retention_days=14,
        reason="poison",
        event_id="evt-old",
    )
    assert keep["expired"] is False
    assert keep["action"] == "keep"
    assert expire["expired"] is True
    assert expire["action"] == "expire"
    assert expire["age_days"] > 14


def test_plan_counts() -> None:
    as_of = datetime(2026, 9, 1, tzinfo=UTC)
    plan = plan_retention(
        [
            {"written_at": "2026-08-31T00:00:00+00:00", "reason": "schema"},
            {"written_at": "2026-07-01T00:00:00+00:00", "reason": "poison"},
        ],
        as_of=as_of,
        retention_days=14,
    )
    assert plan["keep_count"] == 1
    assert plan["expire_count"] == 1
    assert plan["dataset"] == DATASET_ID
    assert plan["cutoff"].startswith("2026-08-18")


def test_spec_snapshot_includes_expired_fixture() -> None:
    as_of = datetime(2026, 9, 1, tzinfo=UTC)
    snap = spec_snapshot(as_of=as_of, retention_days=14)
    assert snap["backend"] == "spec"
    assert snap["keep_count"] == 2
    assert snap["expire_count"] == 1
    assert snap["expire"][0]["reason"] == "poison"
    assert snap["apply"] is False


def test_collect_and_describe() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    result = describe_quarantine_retention()
    assert result["dataset"] == DATASET_ID
    assert result["retention_days"] == DEFAULT_RETENTION_DAYS or result["retention_days"] > 0
    assert result["keep_count"] + result["expire_count"] >= 1


def test_resolve_env_override(monkeypatch: object) -> None:
    monkeypatch.setenv("LAKEHOUSE_QUARANTINE_RETENTION_DAYS", "7")  # type: ignore[attr-defined]
    assert resolve_retention_days() == 7
    assert resolve_retention_days(3) == 3


def test_cli_quarantine_retention(capsys: object) -> None:
    code = main(["quarantine-retention"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"dataset": "silver.quarantine"' in captured.out
    assert '"retention_days"' in captured.out
    assert code == 0


def test_age_boundary_is_keep() -> None:
    as_of = datetime(2026, 9, 1, tzinfo=UTC)
    written = as_of - timedelta(days=14)
    row = classify_object(written_at=written, as_of=as_of, retention_days=14)
    assert row["expired"] is False
