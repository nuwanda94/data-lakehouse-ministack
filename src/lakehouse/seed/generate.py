"""Deterministic synthetic commerce events for local demos and tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lakehouse.models import CommerceEvent

_EVENT_TYPES = ("page_view", "add_to_cart", "purchase", "refund")
_SKUS = ("SKU-100", "SKU-200", "SKU-300", "SKU-400")
_COUNTRIES = ("US", "DE", "IN", "BR", "JP")


def generate_events(
    count: int = 100,
    *,
    start: datetime | None = None,
    seed: int = 42,
) -> list[CommerceEvent]:
    """Return `count` events. Sequence is deterministic for a given seed."""
    if count < 0:
        raise ValueError("count must be >= 0")
    origin = start or datetime(2026, 1, 1, tzinfo=UTC)
    events: list[CommerceEvent] = []
    for i in range(count):
        n = (seed * 1103515245 + i * 12345) & 0x7FFFFFFF
        events.append(
            CommerceEvent(
                event_id=f"evt-{seed:04d}-{i:06d}",
                event_ts=origin + timedelta(minutes=i),
                event_type=_EVENT_TYPES[n % len(_EVENT_TYPES)],
                user_id=f"user-{(n // 7) % 50:03d}",
                sku=_SKUS[n % len(_SKUS)],
                quantity=(n % 5) + 1,
                amount_usd=round(((n % 90) + 10) * 1.25, 2),
                country=_COUNTRIES[n % len(_COUNTRIES)],
            )
        )
    return events
