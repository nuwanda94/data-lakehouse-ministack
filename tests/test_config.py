from __future__ import annotations

import os
from pathlib import Path

import pytest

from lakehouse import Settings, load_settings
from lakehouse.config import find_env_file, load_dotenv, parse_dotenv

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
)


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _SETTING_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_load_settings_uses_documented_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    settings = load_settings(load_env_file=False)
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

    settings = load_settings(load_env_file=False)
    assert settings.bronze_bucket == "custom-bronze"
    assert settings.aws_region == "eu-west-1"
    assert isinstance(settings, Settings)


def test_empty_required_setting_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRONZE_BUCKET", "")
    with pytest.raises(ValueError, match="BRONZE_BUCKET"):
        load_settings(load_env_file=False)


def test_parse_dotenv_handles_export_quotes_and_comments() -> None:
    text = """
# comment
export BRONZE_BUCKET='from-file'
SILVER_BUCKET='also-from-file'
GOLD_BUCKET=plain
INVALID LINE
"""
    parsed = parse_dotenv(text)
    assert parsed["BRONZE_BUCKET"] == "from-file"
    assert parsed["SILVER_BUCKET"] == "also-from-file"
    assert parsed["GOLD_BUCKET"] == "plain"
    assert "INVALID" not in parsed

    double_quoted = parse_dotenv('GOLD_BUCKET="gold-quoted"\n')
    assert double_quoted["GOLD_BUCKET"] == "gold-quoted"


def test_load_dotenv_does_not_override_existing_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BRONZE_BUCKET=from-dotenv\nSILVER_BUCKET=silver-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("BRONZE_BUCKET", "already-set")
    monkeypatch.delenv("SILVER_BUCKET", raising=False)

    loaded = load_dotenv(env_file, override=False)
    assert loaded == env_file
    assert os.environ["BRONZE_BUCKET"] == "already-set"
    assert os.environ["SILVER_BUCKET"] == "silver-dotenv"


def test_load_settings_reads_explicit_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_settings_env(monkeypatch)
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "BRONZE_BUCKET=file-bronze\nAWS_DEFAULT_REGION=ap-south-1\n",
        encoding="utf-8",
    )

    settings = load_settings(env_file=env_file)
    assert settings.bronze_bucket == "file-bronze"
    assert settings.aws_region == "ap-south-1"
    assert settings.gold_bucket == "lakehouse-local-gold"


def test_find_env_file_walks_parents(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    env_file = tmp_path / ".env"
    env_file.write_text("X=1\n", encoding="utf-8")
    assert find_env_file(start=nested) == env_file.resolve()
