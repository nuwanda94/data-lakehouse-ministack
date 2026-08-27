"""Shared AWS / MiniStack client factory.

All service clients should go through `session()` so endpoint, region, and
credentials stay consistent across seed scripts and pipeline steps.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.client import BaseClient

from lakehouse.config import Settings, get_settings


def _kwargs(settings: Settings) -> dict[str, Any]:
    return {
        "region_name": settings.region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "endpoint_url": settings.endpoint_url,
    }


@lru_cache(maxsize=1)
def session(settings: Settings | None = None) -> boto3.Session:
    cfg = settings or get_settings()
    return boto3.Session(
        region_name=cfg.region,
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
    )


def client(service: str, settings: Settings | None = None) -> BaseClient:
    cfg = settings or get_settings()
    return session(cfg).client(service, endpoint_url=cfg.endpoint_url)


def resource(service: str, settings: Settings | None = None) -> Any:
    cfg = settings or get_settings()
    return session(cfg).resource(service, endpoint_url=cfg.endpoint_url)


def s3_client(settings: Settings | None = None) -> BaseClient:
    return client("s3", settings)


def sqs_client(settings: Settings | None = None) -> BaseClient:
    return client("sqs", settings)


def dynamodb_client(settings: Settings | None = None) -> BaseClient:
    return client("dynamodb", settings)


def lambda_client(settings: Settings | None = None) -> BaseClient:
    return client("lambda", settings)
