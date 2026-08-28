"""Declarative quality gate for Silver (and raw) event batches.

The gate is the first-class step between Silver and Gold: it can pass the
batch, fail the pipeline run, or quarantine failing rows so Gold never
sees them. Checks are named and stable so later contract tests / CI can
assert on the same identifiers.

Pandera / Great Expectations stay optional; the default implementation is
pure Python + Pydantic so Lambda packaging stays small.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from lakehouse.models import CommerceEvent, QualityResult
from lakehouse.transforms.events import KNOWN_EVENT_TYPES

QualityAction = Literal["pass", "fail", "quarantine"]
OnFail = Literal["fail", "quarantine"]


@dataclass
class FailingRow:
    """A record that failed one or more named checks."""

    payload: dict[str, Any]
    reasons: list[str]


@dataclass
class QualityDecision:
    """Outcome of evaluating a quality gate over a batch."""

    passed: bool
    action: QualityAction
    results: list[QualityResult]
    failed_rows: list[FailingRow] = field(default_factory=list)
    rows_scanned: int = 0
    rows_failed: int = 0

    @property
    def failed_checks(self) -> list[QualityResult]:
        return [r for r in self.results if not r.passed]

    @property
    def fail_ratio(self) -> float:
        if self.rows_scanned == 0:
            return 0.0
        return self.rows_failed / self.rows_scanned


def _as_payload(record: dict[str, Any] | CommerceEvent) -> dict[str, Any]:
    if isinstance(record, CommerceEvent):
        return record.model_dump(mode="json")
    return dict(record)


def _row_failures(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    event_id = str(payload.get("event_id") or "").strip()
    if not event_id:
        reasons.append("event_id_present")

    event_type = str(payload.get("event_type") or "").strip()
    if event_type not in KNOWN_EVENT_TYPES:
        reasons.append("known_event_type")

    user_id = str(payload.get("user_id") or "").strip()
    sku = str(payload.get("sku") or "").strip()
    if not user_id or not sku:
        reasons.append("required_dimensions")

    try:
        quantity = int(payload.get("quantity", 0))
        amount = float(payload.get("amount_usd", 0))
    except (TypeError, ValueError):
        reasons.append("quantity_and_amount_sane")
    else:
        if quantity <= 0 or amount < 0:
            reasons.append("quantity_and_amount_sane")

    try:
        CommerceEvent.model_validate(payload)
    except ValidationError:
        reasons.append("schema_valid")

    return reasons


def evaluate_quality(
    records: Sequence[dict[str, Any] | CommerceEvent],
    *,
    on_fail: OnFail = "fail",
    max_fail_ratio: float = 0.0,
) -> QualityDecision:
    """Run named checks over ``records`` and decide pass / fail / quarantine.

    ``max_fail_ratio`` is the highest allowed fraction of rows that fail any
    check (0.0 means any failing row fails the gate). Empty input is a pass
    so an idle Silver prefix does not block Gold.
    """

    rows = [_as_payload(r) for r in records]
    scanned = len(rows)
    failed_rows: list[FailingRow] = []
    tallies = {
        "event_id_present": 0,
        "known_event_type": 0,
        "required_dimensions": 0,
        "quantity_and_amount_sane": 0,
        "schema_valid": 0,
    }

    for payload in rows:
        reasons = _row_failures(payload)
        if reasons:
            failed_rows.append(FailingRow(payload=payload, reasons=reasons))
            for name in set(reasons):
                if name in tallies:
                    tallies[name] += 1

    rows_failed = len(failed_rows)
    results = [
        QualityResult(
            check_name=name,
            passed=count == 0,
            rows_scanned=scanned,
            rows_failed=count,
        )
        for name, count in tallies.items()
    ]

    ratio = (rows_failed / scanned) if scanned else 0.0
    breached = ratio > max_fail_ratio and rows_failed > 0
    if not breached:
        action: QualityAction = "pass"
        passed = True
    else:
        action = "quarantine" if on_fail == "quarantine" else "fail"
        passed = False

    return QualityDecision(
        passed=passed,
        action=action,
        results=results,
        failed_rows=failed_rows,
        rows_scanned=scanned,
        rows_failed=rows_failed,
    )


def run_quality_checks(events: Sequence[CommerceEvent]) -> list[QualityResult]:
    """Back-compat wrapper used by the local pipeline runner."""

    return evaluate_quality(events).results
