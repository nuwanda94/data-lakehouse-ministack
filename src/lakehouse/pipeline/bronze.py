"""Bronze zone helpers — raw JSON landing keys."""

from __future__ import annotations

from datetime import datetime

from lakehouse.models import CommerceEvent


def bronze_key(event: CommerceEvent, *, prefix: str = "events") -> str:
    """Object key: events/dt=YYYY-MM-DD/event_id.json"""
    ts: datetime = event.event_ts
    day = ts.date().isoformat()
    return f"{prefix}/dt={day}/{event.event_id}.json"
