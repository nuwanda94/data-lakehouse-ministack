"""Gold zone helpers — aggregated metric object keys."""

from __future__ import annotations


def gold_key(*, metric: str, day: str, prefix: str = "metrics") -> str:
    return f"{prefix}/metric={metric}/dt={day}/part-000.json"


def gold_quarantine_key(
    *,
    reason: str,
    metric: str,
    day: str,
    prefix: str = "quarantine",
) -> str:
    """Hive-style key for a rejected Gold metric that must not land in metrics/."""

    safe_reason = (reason or "rejected_metric").replace("/", "_")
    safe_metric = (metric or "unknown").replace("/", "_")
    safe_day = day or "unknown"
    return f"{prefix}/reason={safe_reason}/metric={safe_metric}/dt={safe_day}/part-000.json"
