"""Operator helpers for listing / fetching pipeline runs from DynamoDB."""

from __future__ import annotations

from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings
from lakehouse.pipeline.runs import get_run, list_runs, run_as_dict


def query_runs(
    *,
    settings: Settings | None = None,
    run_id: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    resolved = settings or load_settings()
    ddb = client("dynamodb", resolved)
    table = resolved.pipeline_runs_table
    if run_id:
        run = get_run(ddb, table, run_id)
        return {
            "table": table,
            "run": run_as_dict(run) if run else None,
            "found": run is not None,
        }
    runs = list_runs(ddb, table, limit=limit)
    return {
        "table": table,
        "count": len(runs),
        "runs": [run_as_dict(r) for r in runs],
    }
