"""Lightweight behavior tests that lock the layout contracts."""

from __future__ import annotations

from lakehouse.cli import main
from lakehouse.config import Settings, get_settings
from lakehouse.pipeline import bronze_key, gold_key, run_quality_checks, silver_key
from lakehouse.seed import generate_events


def test_settings_defaults_match_env_example() -> None:
    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.bronze_bucket == "lakehouse-local-bronze"
    assert settings.silver_bucket == "lakehouse-local-silver"
    assert settings.gold_bucket == "lakehouse-local-gold"
    assert settings.endpoint_url.startswith("http://")


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


def test_cli_version_and_config(capsys) -> None:
    assert main(["version"]) == 0
    ver = capsys.readouterr().out.strip()
    assert ver

    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert "bronze_bucket" in out
