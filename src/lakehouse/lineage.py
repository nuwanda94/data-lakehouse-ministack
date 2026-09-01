"""Dataset lineage for one medallion run.

MiniStack CI is hermetic, so this module always builds a spec graph
(Bronze raw → Silver cleansed → quality report → Gold metrics + run row)
and optionally folds in live DynamoDB runs and S3 object counts.

``python -m lakehouse lineage`` prints JSON. ``--out`` writes Mermaid.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings


def _endpoint_reachable(url: str | None, timeout: float = 0.4) -> bool:
    """Cheap TCP probe so unit tests do not block on a down MiniStack."""

    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


ZONES = ("bronze", "silver", "quality", "gold", "runs")

SPEC_EDGES: tuple[tuple[str, str, str], ...] = (
    ("bronze", "silver", "cleanse"),
    ("silver", "quality", "gate"),
    ("quality", "gold", "aggregate"),
    ("bronze", "runs", "run_metadata"),
    ("silver", "runs", "run_metadata"),
    ("quality", "runs", "run_metadata"),
    ("gold", "runs", "run_metadata"),
)


def spec_graph() -> dict[str, Any]:
    """Offline lineage used by unit tests and when MiniStack is down."""

    nodes = [
        {
            "id": "bronze",
            "zone": "bronze",
            "kind": "raw_events",
            "uri": "s3://lakehouse-local-bronze/events/",
            "objects": 20,
        },
        {
            "id": "silver",
            "zone": "silver",
            "kind": "cleansed_events",
            "uri": "s3://lakehouse-local-silver/events/",
            "objects": 18,
        },
        {
            "id": "quality",
            "zone": "silver",
            "kind": "quality_report",
            "uri": "s3://lakehouse-local-silver/quality/",
            "objects": 1,
        },
        {
            "id": "gold",
            "zone": "gold",
            "kind": "daily_metrics",
            "uri": "s3://lakehouse-local-gold/metrics/",
            "objects": 1,
        },
        {
            "id": "runs",
            "zone": "control",
            "kind": "pipeline_run",
            "uri": "dynamodb://lakehouse-local-pipeline-runs",
            "objects": 1,
        },
    ]
    edges = [{"from": src, "to": dst, "relation": rel} for src, dst, rel in SPEC_EDGES]
    return {
        "source": "spec",
        "run_id": "spec-run",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "nodes": nodes,
        "edges": edges,
        "ok": True,
    }


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
        }
    live_runs = _live_runs(resolved)
    bronze_n = _live_object_count(resolved, resolved.bronze_bucket, "events/")
    silver_n = _live_object_count(resolved, resolved.silver_bucket, "events/")
    quality_n = _live_object_count(resolved, resolved.silver_bucket, "quality/")
    gold_n = _live_object_count(resolved, resolved.gold_bucket, "metrics/")
    live_ok = any(v is not None for v in (bronze_n, silver_n, quality_n, gold_n)) or bool(
        live_runs
    )
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
    live = {
        "source": "live",
        "run_id": run_id,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "nodes": live_nodes,
        "edges": spec["edges"],
        "runs_sampled": len(live_runs),
        "ok": live_ok,
    }
    return {
        "backend": "live" if live_ok else "spec",
        "spec": spec,
        "live": live,
        "zones": list(ZONES),
    }


def render_mermaid(snapshot: dict[str, Any] | None = None) -> str:
    """Render a flowchart that reviewers can paste into GitHub / Mermaid."""

    snap = snapshot or collect_snapshot()
    graph = snap["live"] if snap.get("backend") == "live" else snap["spec"]
    lines = ["flowchart LR"]
    for node in graph["nodes"]:
        label = f"{node['id']}\n{node['kind']}"
        if node.get("objects") is not None:
            label += f"\n{node['objects']} objects"
        lines.append(f'  {node["id"]}["{label}"]')
    for edge in graph["edges"]:
        lines.append(f"  {edge['from']} -->|{edge['relation']}| {edge['to']}")
    return "\n".join(lines) + "\n"


def write_mermaid(path: Path, snapshot: dict[str, Any] | None = None) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_mermaid(snapshot), encoding="utf-8")
    return dest


def describe_lineage(*, out: str | None = None) -> dict[str, Any]:
    snap = collect_snapshot()
    graph = snap["live"] if snap["backend"] == "live" else snap["spec"]
    result: dict[str, Any] = {
        "ok": True,
        "backend": snap["backend"],
        "run_id": graph.get("run_id"),
        "node_ids": [n["id"] for n in graph["nodes"]],
        "edge_count": len(graph["edges"]),
        "zones": snap["zones"],
    }
    if out:
        written = write_mermaid(Path(out), snapshot=snap)
        result["mermaid_path"] = str(written)
    return result
