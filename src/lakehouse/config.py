"""Runtime settings loaded from process environment.

`.env` file loading is a follow-up chore; this module only reads `os.environ`
so imports stay free of optional I/O side effects.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULTS = {
    "AWS_ENDPOINT_URL": "http://localhost:4566",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "BRONZE_BUCKET": "lakehouse-local-bronze",
    "SILVER_BUCKET": "lakehouse-local-silver",
    "GOLD_BUCKET": "lakehouse-local-gold",
    "PIPELINE_RUNS_TABLE": "lakehouse-local-pipeline-runs",
    "GOLD_METRICS_TABLE": "lakehouse-local-gold-metrics",
}


def _env(name: str) -> str:
    value = os.environ.get(name, _DEFAULTS[name])
    if not value:
        raise ValueError(f"Required setting {name} is empty")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Typed view of lakehouse + MiniStack connection settings."""

    aws_endpoint_url: str
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    bronze_bucket: str
    silver_bucket: str
    gold_bucket: str
    pipeline_runs_table: str
    gold_metrics_table: str

    @property
    def buckets(self) -> tuple[str, str, str]:
        return (self.bronze_bucket, self.silver_bucket, self.gold_bucket)


def load_settings() -> Settings:
    """Build settings from the current process environment."""

    return Settings(
        aws_endpoint_url=_env("AWS_ENDPOINT_URL"),
        aws_region=_env("AWS_DEFAULT_REGION"),
        aws_access_key_id=_env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("AWS_SECRET_ACCESS_KEY"),
        bronze_bucket=_env("BRONZE_BUCKET"),
        silver_bucket=_env("SILVER_BUCKET"),
        gold_bucket=_env("GOLD_BUCKET"),
        pipeline_runs_table=_env("PIPELINE_RUNS_TABLE"),
        gold_metrics_table=_env("GOLD_METRICS_TABLE"),
    )


get_settings = load_settings
