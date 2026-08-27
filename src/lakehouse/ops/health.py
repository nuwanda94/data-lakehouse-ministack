"""Health checks against MiniStack / AWS."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings


def check_health(settings: Settings | None = None) -> dict[str, Any]:
    """Return a structured health report. Raises on hard connectivity failure."""

    resolved = settings or load_settings()
    report: dict[str, Any] = {
        "endpoint": resolved.aws_endpoint_url,
        "region": resolved.aws_region,
        "s3_ok": False,
        "dynamodb_ok": False,
        "buckets": [],
        "tables": [],
        "errors": [],
    }

    try:
        s3 = client("s3", resolved)
        buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
        report["s3_ok"] = True
        report["buckets"] = buckets
    except (BotoCoreError, ClientError, OSError) as exc:
        report["errors"].append(f"s3: {exc}")

    try:
        ddb = client("dynamodb", resolved)
        tables = ddb.list_tables().get("TableNames", [])
        report["dynamodb_ok"] = True
        report["tables"] = tables
    except (BotoCoreError, ClientError, OSError) as exc:
        report["errors"].append(f"dynamodb: {exc}")

    if not report["s3_ok"] and not report["dynamodb_ok"]:
        joined = "; ".join(report["errors"]) or "unknown error"
        raise RuntimeError(
            f"MiniStack health check failed at {resolved.aws_endpoint_url}: {joined}"
        )
    return report
