"""One-command demo: seed → pipeline → query with assertions.

``make demo`` / ``python -m lakehouse demo`` walks the medallion path and
prints a summary. Two backends:

* ``offline`` — in-memory generate → cleanse → quality → gold. Used by
  unit tests and when MiniStack is down.
* ``live`` — write Bronze via S3, run the local pipeline, query Gold.

``auto`` tries live and falls back to offline when S3/DynamoDB are
unreachable so the CLI still works on a fresh laptop.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from lakehouse.pipeline.quality import run_quality_checks
from lakehouse.seed.generate import generate_events
from lakehouse.transforms.events import aggregate_gold, cleanse_to_silver

DemoMode = Literal["auto", "live", "offline"]


def _assert(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _offline_demo(count: int) -> dict[str, Any]:
    events = generate_events(count)
    watermark = max(e.event_ts for e in events) + timedelta(minutes=1)
    batch = cleanse_to_silver(
        [e.model_dump(mode="json") for e in events],
        watermark=watermark,
        lookback=timedelta(days=3650),
    )
    quality = run_quality_checks(batch.valid)
    failed = [q for q in quality if not q.passed]
    gold = aggregate_gold(batch.valid)
    gold_events = sum(int(row["events"]) for row in gold)
    return {
        "backend": "offline",
        "seeded": len(events),
        "silver_valid": len(batch.valid),
        "silver_quarantined": len(batch.quarantined),
        "quality_failed": [q.check_name for q in failed],
        "gold_rows": gold,
        "gold_event_count": gold_events,
        "run_id": None,
        "query": {
            "gold_objects": [],
            "metrics": gold,
        },
    }


def _live_demo(count: int) -> dict[str, Any]:
    from lakehouse.ops.pipeline import run_pipeline
    from lakehouse.ops.query import query_gold
    from lakehouse.ops.seed import seed_bronze

    seed = seed_bronze(count)
    pipeline = run_pipeline()
    query = query_gold()
    gold_event_count = 0
    for row in query.get("metrics") or []:
        try:
            gold_event_count += int(row.get("events") or 0)
        except (TypeError, ValueError):
            continue
    return {
        "backend": "live",
        "seeded": int(seed.get("written") or 0),
        "silver_valid": int(pipeline.get("silver_written") or 0),
        "silver_quarantined": 0,
        "quality_failed": [
            q.get("check_name")
            for q in (pipeline.get("quality") or [])
            if not q.get("passed", True)
        ],
        "gold_rows": query.get("metrics") or [],
        "gold_event_count": gold_event_count,
        "run_id": pipeline.get("run_id"),
        "query": query,
        "pipeline": {
            "bronze_objects": pipeline.get("bronze_objects"),
            "silver_written": pipeline.get("silver_written"),
            "gold_written": pipeline.get("gold_written"),
        },
    }


def _live_available() -> bool:
    try:
        from lakehouse.ops.health import check_health

        report = check_health()
    except Exception:
        return False
    return bool(report.get("s3_ok") and report.get("dynamodb_ok"))


def _evaluate(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    _assert(int(payload["seeded"]) > 0, "seed produced zero events", failures)
    _assert(int(payload["silver_valid"]) > 0, "silver produced zero valid rows", failures)
    _assert(not payload["quality_failed"], f"quality failed: {payload['quality_failed']}", failures)
    _assert(int(payload["gold_event_count"]) > 0, "gold produced zero events", failures)
    # Offline path is a closed batch: Gold must reconcile 1:1 with Silver.
    # Live Gold tables accumulate across demos, so only require non-empty Gold.
    if payload.get("backend") == "offline":
        _assert(
            int(payload["gold_event_count"]) == int(payload["silver_valid"]),
            "gold event count does not match silver valid count",
            failures,
        )
    return failures


def run_demo(
    *,
    count: int = 20,
    mode: DemoMode = "auto",
) -> dict[str, Any]:
    """Seed → transform → quality → gold and assert the path is healthy."""
    if count < 1:
        raise ValueError("count must be >= 1")

    backend: DemoMode
    if mode == "offline":
        backend = "offline"
    elif mode == "live":
        backend = "live"
    else:
        backend = "live" if _live_available() else "offline"

    if backend == "live":
        try:
            payload = _live_demo(count)
        except Exception as exc:
            if mode == "live":
                raise
            payload = _offline_demo(count)
            payload["fallback_reason"] = str(exc)
    else:
        payload = _offline_demo(count)

    failures = _evaluate(payload)
    payload["ok"] = not failures
    payload["assertions"] = {
        "seeded_gt_zero": int(payload["seeded"]) > 0,
        "silver_valid_gt_zero": int(payload["silver_valid"]) > 0,
        "quality_passed": not payload["quality_failed"],
        "gold_matches_silver": (
            payload.get("backend") != "offline"
            or int(payload["gold_event_count"]) == int(payload["silver_valid"])
        ),
        "failures": failures,
    }
    payload["generated_at"] = datetime.now(tz=UTC).isoformat()
    return payload
