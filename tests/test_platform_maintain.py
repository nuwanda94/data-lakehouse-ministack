from __future__ import annotations

from datetime import date

from lakehouse.cli import main
from lakehouse.platform_maintain import (
    JOB,
    ORDER,
    ZONES,
    collect_snapshot,
    describe_platform_maintain,
    spec_snapshot,
)


def test_spec_snapshot_chains_all_zones() -> None:
    as_of = date(2026, 9, 1)
    snap = spec_snapshot(as_of=as_of)
    assert snap["backend"] == "spec"
    assert snap["job"] == JOB
    assert snap["order"] == list(ORDER)
    assert snap["zones"] == list(ZONES)
    assert snap["expire_count"] == 3
    assert snap["compact_count"] == 3
    assert snap["apply"] is False
    assert snap["ok"] is True
    assert snap["bronze"]["job"] == "bronze.maintain"
    assert snap["silver"]["job"] == "silver.maintain"
    assert snap["gold"]["job"] == "gold.maintain"


def test_collect_and_describe() -> None:
    snap = collect_snapshot(as_of=date(2026, 9, 1))
    assert snap["backend"] in {"live", "spec"}
    assert snap["order"] == list(ORDER)
    result = describe_platform_maintain(as_of=date(2026, 9, 1))
    assert result["job"] == JOB
    assert result["bronze_job"] == "bronze.maintain"
    assert result["silver_job"] == "silver.maintain"
    assert result["gold_job"] == "gold.maintain"
    assert (result["expire_count"] or 0) + (result["compact_count"] or 0) >= 3


def test_cli_platform_maintain(capsys: object) -> None:
    code = main(["platform-maintain"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"job": "platform.maintain"' in captured.out
    assert '"order"' in captured.out
    assert '"expire_count"' in captured.out
    assert '"compact_count"' in captured.out
    assert code == 0
