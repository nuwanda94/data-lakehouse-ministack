from __future__ import annotations

from datetime import date

from lakehouse.cli import main
from lakehouse.silver_retention import (
    DATASET_ID,
    DEFAULT_RETENTION_DAYS,
    classify_partition,
    collect_snapshot,
    describe_silver_retention,
    plan_retention,
    resolve_retention_days,
    spec_snapshot,
)


def test_classify_keep_and_expire() -> None:
    as_of = date(2026, 9, 1)
    keep = classify_partition(
        dt="2026-07-20",
        as_of=as_of,
        retention_days=60,
    )
    expire = classify_partition(
        dt="2026-06-01",
        as_of=as_of,
        retention_days=60,
    )
    assert keep["expired"] is False
    assert keep["action"] == "keep"
    assert expire["expired"] is True
    assert expire["action"] == "expire"
    assert expire["age_days"] == 92


def test_plan_counts() -> None:
    as_of = date(2026, 9, 1)
    plan = plan_retention(
        [
            {"dt": "2026-08-31", "objects": 4},
            {"dt": "2026-06-01", "objects": 2},
        ],
        as_of=as_of,
        retention_days=60,
    )
    assert plan["keep_count"] == 1
    assert plan["expire_count"] == 1
    assert plan["cutoff"] == "2026-07-03"
    assert plan["dataset"] == DATASET_ID


def test_spec_snapshot_includes_expired_fixture() -> None:
    as_of = date(2026, 9, 1)
    snap = spec_snapshot(as_of=as_of, retention_days=60)
    assert snap["backend"] == "spec"
    assert snap["keep_count"] == 2
    assert snap["expire_count"] == 1
    assert snap["expire"][0]["dt"] == "2026-06-28"
    assert snap["apply"] is False


def test_collect_and_describe() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    result = describe_silver_retention()
    assert result["dataset"] == DATASET_ID
    assert result["retention_days"] == DEFAULT_RETENTION_DAYS or result["retention_days"] > 0
    assert result["keep_count"] + result["expire_count"] >= 1


def test_resolve_env_override(monkeypatch: object) -> None:
    monkeypatch.setenv("LAKEHOUSE_SILVER_RETENTION_DAYS", "21")  # type: ignore[attr-defined]
    assert resolve_retention_days() == 21
    assert resolve_retention_days(7) == 7


def test_cli_silver_retention(capsys: object) -> None:
    code = main(["silver-retention"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"dataset": "silver.cleaned_events"' in captured.out
    assert '"retention_days"' in captured.out
    assert code == 0


def test_age_boundary_is_keep() -> None:
    as_of = date(2026, 9, 1)
    row = classify_partition(dt="2026-07-03", as_of=as_of, retention_days=60)
    assert row["expired"] is False
