"""Gold-zone Lambda: aggregate Silver events into daily metrics."""

from lakehouse.gold.handler import handler, run_gold, transform_gold

__all__ = ["handler", "run_gold", "transform_gold"]
