"""Quality-check facade used by the local runner and zone Lambdas."""

from lakehouse.quality.gate import evaluate_quality, run_quality_checks

__all__ = ["evaluate_quality", "run_quality_checks"]
