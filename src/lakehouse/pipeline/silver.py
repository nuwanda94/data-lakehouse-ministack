"""Silver zone helpers — cleaned / conformed object keys."""

from __future__ import annotations

from lakehouse.models import CommerceEvent


def silver_key(event: CommerceEvent, *, prefix: str = "events") -> str:
    day = event.event_ts.date().isoformat()
    return f"{prefix}/event_type={event.event_type}/dt={day}/{event.event_id}.json"
