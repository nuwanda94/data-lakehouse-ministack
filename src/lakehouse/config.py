"""Environment-backed settings for local MiniStack and (later) real AWS."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values come from env vars or a `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    aws_endpoint_url: str = Field(default="http://localhost:4566")
    aws_default_region: str = Field(default="us-east-1")
    aws_access_key_id: str = Field(default="test")
    aws_secret_access_key: str = Field(default="test")

    bronze_bucket: str = Field(default="lakehouse-local-bronze")
    silver_bucket: str = Field(default="lakehouse-local-silver")
    gold_bucket: str = Field(default="lakehouse-local-gold")
    pipeline_runs_table: str = Field(default="lakehouse-local-pipeline-runs")
    gold_metrics_table: str = Field(default="lakehouse-local-gold-metrics")

    @property
    def endpoint_url(self) -> str:
        return self.aws_endpoint_url

    @property
    def region(self) -> str:
        return self.aws_default_region


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings. Call `get_settings.cache_clear()` in tests."""
    return Settings()
