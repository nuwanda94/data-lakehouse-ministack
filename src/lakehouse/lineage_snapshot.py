"""Live snapshot helpers for dataset lineage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lakehouse.config import Settings, load_settings
from lakehouse.lineage import (
    SPEC_EDGES,
    ZONES,
    _endpoint_reachable,
    attach_edge_weights,
    path_ratio_alert,
    path_ratios,
    quarantine_subgraph,
    spec_graph,
)


def _live_object_count(settings: Settings, bucket: str, prefix: str) -> int | None:
    try:
        from lakehouse.aws import client
        from lakehouse.storage import list_keys

        s3 = client("s3", settings)
        return len(list_keys(s3, bucket, prefix))
    except Exception:  # noqa: BLE001
        return None


def _live_runs(settings: Settings) -> list[dict[str, Any]]:
    try:
        from lakehouse.ops.runs import query_runs

        payload = query_runs(settings=settings, limit=5)
        return list(payload.get("runs") or [])
    except Exception:  # noqa: BLE001
        return []


def collect_snapshot(settings: Settings | None = None) -> dict[str, Any]:
    """Spec graph plus live counts when MiniStack answers."""

    spec = spec_graph()
    resolved = settings or load_settings()
    if not _endpoint_reachable(resolved.aws_endpoint_url):
        return {
            "backend": "spec",
            "spec": spec,
            "live": None,
            "zones": list(ZONES),
            "quarantine_subgraph": spec["quarantine_subgraph"],
            "path_ratios": spec["path_ratios"],
            "path_ratio_alert": spec["path_ratio_alert"],
        }
    live_runs = _live_runs(resolved)
    bronze_n = _live_object_count(resolved, resolved.bronze_bucket, "events/")
    silver_n = _live_object_count(resolved, resolved.silver_bucket, "events/")
    silver_q_n = _live_object_count(resolved, resolved.silver_bucket, "quarantine/")
    quality_n = _live_object_count(resolved, resolved.silver_bucket, "quality/")
    gold_n = _live_object_count(resolved, resolved.gold_bucket, "metrics/")
    gold_q_n = _live_object_count(resolved, resolved.gold_bucket, "quarantine/")
    live_ok = any(
        v is not None for v in (bronze_n, silver_n, silver_q_n, quality_n, gold_n, gold_q_n)
    ) or bool(live_runs)
    live_nodes = [
        {
            "id": "bronze",
            "zone": "bronze",
            "kind": "raw_events",
            "uri": f"s3://{resolved.bronze_bucket}/events/",
            "objects": bronze_n,
        },
        {
            "id": "silver",
            "zone": "silver",
            "kind": "cleansed_events",
            "uri": f"s3://{resolved.silver_bucket}/events/",
            "objects": silver_n,
        },
        {
            "id": "silver_quarantine",
            "zone": "silver",
            "kind": "quality_quarantine",
            "uri": f"s3://{resolved.silver_bucket}/quarantine/",
            "objects": silver_q_n,
        },
        {
            "id": "quality",
            "zone": "silver",
            "kind": "quality_report",
            "uri": f"s3://{resolved.silver_bucket}/quality/",
            "objects": quality_n,
        },
        {
            "id": "gold",
            "zone": "gold",
            "kind": "daily_metrics",
            "uri": f"s3://{resolved.gold_bucket}/metrics/",
            "objects": gold_n,
        },
        {
            "id": "gold_quarantine",
            "zone": "gold",
            "kind": "rejected_metrics",
            "uri": f"s3://{resolved.gold_bucket}/quarantine/",
            "objects": gold_q_n,
        },
        {
            "id": "runs",
            "zone": "control",
            "kind": "pipeline_run",
            "uri": f"dynamodb://{resolved.pipeline_runs_table}",
            "objects": len(live_runs) if live_runs else None,
        },
    ]
    run_id = None
    if live_runs:
        first = live_runs[0]
        if isinstance(first, dict):
            run_id = first.get("run_id")
    live_edges = attach_edge_weights(
        live_nodes,
        [{"from": src, "to": dst, "relation": rel} for src, dst, rel in SPEC_EDGES],
    )
    live = {
        "source": "live",
        "run_id": run_id,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "nodes": live_nodes,
        "edges": live_edges,
        "runs_sampled": len(live_runs),
        "ok": live_ok,
    }
    live["quarantine_subgraph"] = quarantine_subgraph(live)
    live["path_ratios"] = path_ratios(live)
    live["path_ratio_alert"] = path_ratio_alert(live["path_ratios"])
    live["ok"] = bool(live_ok) and bool(live["path_ratio_alert"]["ok"])
    return {
        "backend": "live" if live_ok else "spec",
        "spec": spec,
        "live": live,
        "zones": list(ZONES),
        "quarantine_subgraph": live["quarantine_subgraph"]
        if live_ok
        else spec["quarantine_subgraph"],
        "path_ratios": live["path_ratios"] if live_ok else spec["path_ratios"],
        "path_ratio_alert": live["path_ratio_alert"]
        if live_ok
        else spec["path_ratio_alert"],
    }
