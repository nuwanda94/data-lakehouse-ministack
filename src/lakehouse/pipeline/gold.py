"""Gold zone helpers — aggregated metric object keys."""

from __future__ import annotations


def gold_key(*, metric: str, day: str, prefix: str = "metrics") -> str:
    return f"{prefix}/metric={metric}/dt={day}/part-000.json"
