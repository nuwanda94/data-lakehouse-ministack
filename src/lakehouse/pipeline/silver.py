"""Silver zone helpers — cleaned / conformed object keys."""

from __future__ import annotations

from lakehouse.models import CommerceEvent
from lakehouse.transforms.events import QuarantineRow


def silver_key(event: CommerceEvent, *, prefix: str = "events") -> str:
    day = event.event_ts.date().isoformat()
    return f"{prefix}/event_type={event.event_type}/dt={day}/{event.event_id}.json"


def quarantine_key(row: QuarantineRow, *, prefix: str = "quarantine") -> str:
    """Stable key for a rejected bronze record."""

    event_id = str(row.payload.get("event_id") or "unknown").strip() or "unknown"
    reason = row.reason.replace("/", "_")
    return f"{prefix}/reason={reason}/{event_id}.json"
