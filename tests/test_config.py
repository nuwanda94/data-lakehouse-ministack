from __future__ import annotations

import pytest

from lakehouse import Settings, load_settings


def test_load_settings_uses_documented_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AWS_ENDPOINT_URL",
        "AWS_DEFAULT_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "BRONZE_BUCKET",
        "SILVER_BUCKET",
        "GOLD_BUCKET",
        "PIPELINE_RUNS_TABLE",
        "GOLD_METRICS_TABLE",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()
    assert settings.aws_endpoint_url == "http://localhost:4566"
    assert settings.aws_region == "us-east-1"
    assert settings.buckets == (
        "lakehouse-local-bronze",
        "lakehouse-local-silver",
        "lakehouse-local-gold",
    )
    assert settings.pipeline_runs_table == "lakehouse-local-pipeline-runs"


def test_load_settings_respects_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRONZE_BUCKET", "custom-bronze")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    settings = load_settings()
    assert settings.bronze_bucket == "custom-bronze"
    assert settings.aws_region == "eu-west-1"
    assert isinstance(settings, Settings)


def test_empty_required_setting_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRONZE_BUCKET", "")
    with pytest.raises(ValueError, match="BRONZE_BUCKET"):
        load_settings()
