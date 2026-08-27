"""First-pass quality checks over in-memory event batches."""

from __future__ import annotations

from collections.abc import Sequence

from lakehouse.models import CommerceEvent, QualityResult


def run_quality_checks(events: Sequence[CommerceEvent]) -> list[QualityResult]:
    rows = list(events)
    scanned = len(rows)

    missing_id = sum(1 for e in rows if not e.event_id)
    non_positive = sum(1 for e in rows if e.quantity <= 0 or e.amount_usd < 0)
    unknown_type = sum(
        1 for e in rows if e.event_type not in {"page_view", "add_to_cart", "purchase", "refund"}
    )

    return [
        QualityResult(
            check_name="event_id_present",
            passed=missing_id == 0,
            rows_scanned=scanned,
            rows_failed=missing_id,
        ),
        QualityResult(
            check_name="quantity_and_amount_sane",
            passed=non_positive == 0,
            rows_scanned=scanned,
            rows_failed=non_positive,
        ),
        QualityResult(
            check_name="known_event_type",
            passed=unknown_type == 0,
            rows_scanned=scanned,
            rows_failed=unknown_type,
        ),
    ]
