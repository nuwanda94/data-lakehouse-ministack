"""Pure bronze → silver → gold transforms (no I/O).

These functions are the unit-testable core of the medallion path. The
local Python runner (`lakehouse.ops.pipeline`) and future Lambdas should
call them rather than reimplementing cleansing or aggregation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from lakehouse.models import CommerceEvent

KNOWN_EVENT_TYPES = frozenset({"page_view", "add_to_cart", "purchase", "refund"})


@dataclass(frozen=True)
class QuarantineRow:
    """A bronze record that failed validation plus a short reason."""

    payload: dict[str, Any]
    reason: str


@dataclass
class SilverBatch:
    valid: list[CommerceEvent] = field(default_factory=list)
    quarantined: list[QuarantineRow] = field(default_factory=list)
    late: list[CommerceEvent] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.valid and not self.quarantined and not self.late


def parse_bronze_record(payload: dict[str, Any]) -> CommerceEvent:
    """Validate a raw bronze JSON object into a CommerceEvent.

    Raises ValueError with a stable reason string so callers can quarantine.
    """
    if not payload:
        raise ValueError("empty_record")
    event_id = str(payload.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("missing_event_id")
    event_type = str(payload.get("event_type") or "").strip()
    if event_type not in KNOWN_EVENT_TYPES:
        raise ValueError("unknown_event_type")
    try:
        quantity = int(payload.get("quantity", 0))
        amount = float(payload.get("amount_usd", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("non_numeric_measures") from exc
    if quantity <= 0:
        raise ValueError("non_positive_quantity")
    if amount < 0:
        raise ValueError("negative_amount")
    try:
        return CommerceEvent.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("schema_invalid") from exc


def is_late(
    event: CommerceEvent,
    *,
    watermark: datetime,
    lookback: timedelta,
) -> bool:
    """True when event_ts is older than watermark - lookback.

    Late arrivals are still valid commerce events; they are tagged so a
    later reprocessing window can reopen the affected gold partitions.
    """
    cutoff = watermark - lookback
    ts = event.event_ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    return ts < cutoff


def cleanse_to_silver(
    records: Sequence[dict[str, Any] | CommerceEvent],
    *,
    watermark: datetime | None = None,
    lookback: timedelta = timedelta(days=2),
) -> SilverBatch:
    """Split a bronze batch into valid, quarantined, and late events.

    Empty input yields an empty batch (not an error). All-invalid input
    yields only quarantined rows.
    """
    batch = SilverBatch()
    wm = watermark or datetime.now(tz=UTC)
    for raw in records:
        if isinstance(raw, CommerceEvent):
            payload = raw.model_dump(mode="json")
            event = raw
            try:
                parse_bronze_record(payload)
            except ValueError as exc:
                batch.quarantined.append(QuarantineRow(payload=payload, reason=str(exc)))
                continue
        else:
            payload = dict(raw)
            try:
                event = parse_bronze_record(payload)
            except ValueError as exc:
                batch.quarantined.append(QuarantineRow(payload=payload, reason=str(exc)))
                continue
        if is_late(event, watermark=wm, lookback=lookback):
            batch.late.append(event)
        else:
            batch.valid.append(event)
    return batch


def aggregate_gold(events: Iterable[CommerceEvent]) -> list[dict[str, Any]]:
    """Daily metrics by event_type. Empty input → empty list."""
    by_day_type: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"events": 0, "amount_usd": 0.0}
    )
    for event in events:
        day = event.event_ts.date().isoformat()
        bucket = by_day_type[(day, event.event_type)]
        bucket["events"] += 1
        bucket["amount_usd"] += event.amount_usd
    return [
        {
            "dt": day,
            "event_type": event_type,
            "events": int(stats["events"]),
            "amount_usd": round(stats["amount_usd"], 2),
        }
        for (day, event_type), stats in sorted(by_day_type.items())
    ]
