"""boto3 session / client factory pointed at MiniStack or real AWS."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from lakehouse.config import Settings, load_settings


def _client_kwargs(settings: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return kwargs


def client(service: str, settings: Settings | None = None) -> Any:
    """Return a boto3 client for `service` using lakehouse settings."""

    resolved = settings or load_settings()
    return boto3.client(service, **_client_kwargs(resolved))


@lru_cache(maxsize=8)
def cached_client(service: str) -> Any:
    """Process-wide client cache for CLI / seed scripts."""

    return client(service)
