"""Lightweight behavior tests that lock the layout contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from lakehouse.cli import main
from lakehouse.config import load_settings
from lakehouse.pipeline import bronze_key, gold_key, run_quality_checks, silver_key
from lakehouse.seed import generate_events

_SETTING_KEYS = (
    "AWS_ENDPOINT_URL",
    "AWS_DEFAULT_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "BRONZE_BUCKET",
    "SILVER_BUCKET",
    "GOLD_BUCKET",
    "PIPELINE_RUNS_TABLE",
    "GOLD_METRICS_TABLE",
    "BRONZE_EVENTS_QUEUE",
    "BRONZE_EVENTS_QUEUE_URL",
)


def test_settings_defaults_match_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults must match .env.example when process env is clean."""
    for key in _SETTING_KEYS:
        monkeypatch.delenv(key, raising=False)
    settings = load_settings(load_env_file=False)
    assert settings.bronze_bucket == "lakehouse-local-bronze"
    assert settings.silver_bucket == "lakehouse-local-silver"
    assert settings.gold_bucket == "lakehouse-local-gold"
    assert settings.aws_endpoint_url.startswith("http://")


def test_generate_events_is_deterministic() -> None:
    a = generate_events(5, seed=7)
    b = generate_events(5, seed=7)
    assert [e.event_id for e in a] == [e.event_id for e in b]
    assert a[0].event_id.startswith("evt-0007-")


def test_zone_keys_and_quality() -> None:
    events = generate_events(3, seed=1)
    event = events[0]
    assert bronze_key(event).startswith("events/dt=")
    assert "event_type=" in silver_key(event)
    assert gold_key(metric="gmv", day="2026-01-01").endswith("part-000.json")
    results = run_quality_checks(events)
    assert results and all(r.passed for r in results)


def test_contributing_and_codeowners_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    owners = (root / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "Conventional commits" in contributing
    assert "@nuwanda94" in owners


def test_cli_version_and_config(capsys) -> None:
    assert main(["--version"]) == 0
    ver = capsys.readouterr().out.strip()
    assert ver

    assert main(["settings"]) == 0
    out = capsys.readouterr().out
    assert "bronze_bucket" in out
