from __future__ import annotations

import json

from lakehouse.cli import main
from lakehouse.ops.demo import run_demo


def test_offline_demo_passes_assertions() -> None:
    result = run_demo(count=24, mode="offline")
    assert result["ok"] is True
    assert result["backend"] == "offline"
    assert result["seeded"] == 24
    assert result["silver_valid"] == 24
    assert result["gold_event_count"] == 24
    assert result["assertions"]["quality_passed"] is True
    assert result["assertions"]["gold_matches_silver"] is True
    assert result["assertions"]["failures"] == []
    assert result["gold_rows"]


def test_offline_demo_rejects_empty_count() -> None:
    try:
        run_demo(count=0, mode="offline")
    except ValueError as exc:
        assert "count" in str(exc)
    else:
        raise AssertionError("expected ValueError for count=0")


def test_cli_demo_offline(capsys: object) -> None:
    assert main(["demo", "--mode", "offline", "--count", "8"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["backend"] == "offline"
    assert payload["seeded"] == 8
