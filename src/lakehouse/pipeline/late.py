"""Late-arriving data windows and partition selection.

Gold daily metrics are keyed by event_ts date, not ingest time. An event
that lands after the original Gold run must reopen that day so the
aggregate is recomputed from the full Silver partition, not just the
late row.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from lakehouse.models import CommerceEvent

_DT_RE = re.compile(r"(?:^|/)dt=(\d{4}-\d{2}-\d{2})(?:/|$)")


def parse_lookback_days(value: str | int | None, *, default: int = 2) -> int:
    """Parse LOOKBACK_DAYS. Zero is allowed; negatives fall back to default."""

    if value is None or value == "":
        return default
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    if days < 0:
        return default
    return days


def lookback_delta(days: int) -> timedelta:
    return timedelta(days=days)


def as_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        ts = value
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC).date()
    return value


def window_bounds(
    *,
    as_of: datetime | date | None = None,
    lookback_days: int = 2,
) -> tuple[date, date]:
    """Inclusive [start, end] calendar dates covered by the lookback window."""

    end = as_date(as_of or datetime.now(tz=UTC))
    start = end - timedelta(days=lookback_days)
    return start, end


def date_in_window(day: date, *, start: date, end: date) -> bool:
    return start <= day <= end


def event_in_window(
    event: CommerceEvent,
    *,
    start: date,
    end: date,
) -> bool:
    return date_in_window(as_date(event.event_ts), start=start, end=end)


def dt_from_key(key: str) -> str | None:
    """Extract a Hive ``dt=YYYY-MM-DD`` partition from an object key."""

    match = _DT_RE.search(key)
    if match is None:
        return None
    return match.group(1)


def key_in_window(key: str, *, start: date, end: date) -> bool:
    raw = dt_from_key(key)
    if raw is None:
        return False
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        return False
    return date_in_window(day, start=start, end=end)


def affected_partitions(events: Iterable[CommerceEvent]) -> list[dict[str, str]]:
    """Unique Gold partitions touched by ``events``, sorted."""

    seen: set[tuple[str, str]] = set()
    for event in events:
        seen.add((event.event_type, as_date(event.event_ts).isoformat()))
    return [{"event_type": event_type, "dt": day} for event_type, day in sorted(seen)]


def filter_events_in_window(
    events: Sequence[CommerceEvent],
    *,
    start: date,
    end: date,
) -> list[CommerceEvent]:
    return [event for event in events if event_in_window(event, start=start, end=end)]


def watermark_from_event(event: dict[str, Any] | None) -> datetime | None:
    """Optional override carried on a Lambda / CLI payload."""

    if not event:
        return None
    raw = event.get("watermark") or event.get("as_of")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
