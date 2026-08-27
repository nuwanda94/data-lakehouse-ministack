"""Write synthetic commerce events into the bronze bucket."""

from __future__ import annotations

from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.pipeline.bronze import bronze_key
from lakehouse.seed.generate import generate_events


def seed_bronze(count: int = 50, *, settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or load_settings()
    events = generate_events(count)
    s3 = client("s3", resolved)
    written = 0
    for event in events:
        key = bronze_key(event)
        body = event.model_dump_json()
        s3.put_object(
            Bucket=resolved.bronze_bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        written += 1
    return {
        "bucket": resolved.bronze_bucket,
        "written": written,
        "sample_key": bronze_key(events[0]) if events else None,
    }
