from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lakehouse.cli import main
from lakehouse.sla import (
    DATASET_ID,
    DEFAULT_MAX_AGE_HOURS,
    collect_snapshot,
    describe_sla,
    evaluate,
    spec_snapshot,
)


def test_evaluate_fresh_is_ok() -> None:
    now = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    result = evaluate(
        last_written=now - timedelta(hours=2),
        as_of=now,
        max_age_hours=24,
    )
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["dataset"] == DATASET_ID
    assert result["age_hours"] == 2.0
    assert result["max_age_hours"] == 24


def test_evaluate_stale_is_breached() -> None:
    now = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    result = evaluate(
        last_written=now - timedelta(hours=30),
        as_of=now,
        max_age_hours=24,
    )
    assert result["ok"] is False
    assert result["status"] == "breached"
    assert result["age_hours"] == 30.0


def test_spec_snapshot_fresh_and_stale() -> None:
    now = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    fresh = spec_snapshot(as_of=now, max_age_hours=24, fresh=True)
    stale = spec_snapshot(as_of=now, max_age_hours=24, fresh=False)
    assert fresh["ok"] is True
    assert fresh["backend"] == "spec"
    assert stale["ok"] is False
    assert stale["checks"][0]["status"] == "breached"


def test_collect_and_describe() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    assert snap["checks"]
    result = describe_sla()
    assert result["dataset"] == DATASET_ID
    assert result["max_age_hours"] == DEFAULT_MAX_AGE_HOURS or result["max_age_hours"] > 0
    assert result["status"] in {"ok", "breached"}


def test_cli_sla(capsys: object) -> None:
    code = main(["sla"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"dataset": "gold.daily_metrics"' in captured.out
    assert '"max_age_hours"' in captured.out
    assert code in {0, 1}
