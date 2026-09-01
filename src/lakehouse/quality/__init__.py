"""Quality gates applied between zones."""

from lakehouse.quality.dashboard import collect_snapshot, describe_dashboard, render_html
from lakehouse.quality.gate import (
    FailingRow,
    QualityDecision,
    evaluate_quality,
    run_quality_checks,
)
from lakehouse.quality.handler import handler, run_quality, run_quality_gate

__all__ = [
    "FailingRow",
    "QualityDecision",
    "evaluate_quality",
    "run_quality_checks",
    "handler",
    "run_quality",
    "run_quality_gate",
    "collect_snapshot",
    "describe_dashboard",
    "render_html",
]
