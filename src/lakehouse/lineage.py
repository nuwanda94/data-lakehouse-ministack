"""Dataset lineage for one medallion run.

MiniStack CI is hermetic, so this module always builds a spec graph
(Bronze raw → Silver cleansed **or** Silver quarantine → quality report →
Gold metrics **or** Gold quarantine rejected-metrics + run row) and
optionally folds in live DynamoDB runs and S3 object counts.

The two quarantine leaves are also exposed as a combined subgraph so
operators can inspect Silver + Gold side paths without walking the
happy-path edges.

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


ZONES = (
    "bronze",
    "silver",
    "silver_quarantine",
    "quality",
    "gold",
    "gold_quarantine",
    "runs",
)

QUARANTINE_NODE_IDS: tuple[str, ...] = ("silver_quarantine", "gold_quarantine")

SPEC_EDGES: tuple[tuple[str, str, str], ...] = (
    ("bronze", "silver", "cleanse"),
    ("bronze", "silver_quarantine", "reject"),
    ("silver", "quality", "gate"),
    ("quality", "silver_quarantine", "quarantine"),
    ("quality", "gold", "aggregate"),
    ("quality", "gold_quarantine", "reject"),
    ("silver", "gold_quarantine", "unreadable"),
    ("bronze", "runs", "run_metadata"),
    ("silver", "runs", "run_metadata"),
    ("silver_quarantine", "runs", "run_metadata"),
    ("quality", "runs", "run_metadata"),
    ("gold", "runs", "run_metadata"),
    ("gold_quarantine", "runs", "run_metadata"),
)


def quarantine_subgraph(graph: dict[str, Any]) -> dict[str, Any]:
    """Silver + Gold quarantine leaves as one inspectable subgraph."""

    node_ids = set(QUARANTINE_NODE_IDS)
    nodes = [n for n in graph.get("nodes") or [] if n.get("id") in node_ids]
    incoming = [e for e in graph.get("edges") or [] if e.get("to") in node_ids]
    outgoing = [e for e in graph.get("edges") or [] if e.get("from") in node_ids]
    objects = sum(int(n.get("objects") or 0) for n in nodes)
    return {
        "id": "quarantine",
        "label": "quarantine side paths",
        "node_ids": list(QUARANTINE_NODE_IDS),
        "nodes": nodes,
        "incoming": incoming,
        "outgoing": outgoing,
        "objects": objects,
    }


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
            "id": "silver_quarantine",
            "zone": "silver",
            "kind": "quality_quarantine",
            "uri": "s3://lakehouse-local-silver/quarantine/",
            "objects": 3,
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
            "id": "gold_quarantine",
            "zone": "gold",
            "kind": "rejected_metrics",
            "uri": "s3://lakehouse-local-gold/quarantine/",
            "objects": 2,
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
    graph = {
        "source": "spec",
        "run_id": "spec-run",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "nodes": nodes,
        "edges": edges,
        "ok": True,
    }
    graph["quarantine_subgraph"] = quarantine_subgraph(graph)
    return graph


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
    live = {
        "source": "live",
        "run_id": run_id,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "nodes": live_nodes,
        "edges": spec["edges"],
        "runs_sampled": len(live_runs),
        "ok": live_ok,
    }
    live["quarantine_subgraph"] = quarantine_subgraph(live)
    return {
        "backend": "live" if live_ok else "spec",
        "spec": spec,
        "live": live,
        "zones": list(ZONES),
        "quarantine_subgraph": live["quarantine_subgraph"]
        if live_ok
        else spec["quarantine_subgraph"],
    }


def render_mermaid(snapshot: dict[str, Any] | None = None) -> str:
    """Render a flowchart that reviewers can paste into GitHub / Mermaid."""

    snap = snapshot or collect_snapshot()
    graph = snap["live"] if snap.get("backend") == "live" else snap["spec"]
    q_ids = set(QUARANTINE_NODE_IDS)
    lines = ["flowchart LR"]
    lines.append('  subgraph quarantine["quarantine side paths"]')
    for node in graph["nodes"]:
        if node["id"] not in q_ids:
            continue
        label = f"{node['id']}\n{node['kind']}"
        if node.get("objects") is not None:
            label += f"\n{node['objects']} objects"
        lines.append(f'    {node["id"]}["{label}"]')
    lines.append("  end")
    for node in graph["nodes"]:
        if node["id"] in q_ids:
            continue
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
    subgraph = snap.get("quarantine_subgraph") or quarantine_subgraph(graph)
    result: dict[str, Any] = {
        "ok": True,
        "backend": snap["backend"],
        "run_id": graph.get("run_id"),
        "node_ids": [n["id"] for n in graph["nodes"]],
        "edge_count": len(graph["edges"]),
        "zones": snap["zones"],
        "quarantine_subgraph": {
            "id": subgraph["id"],
            "label": subgraph["label"],
            "node_ids": subgraph["node_ids"],
            "incoming_count": len(subgraph["incoming"]),
            "outgoing_count": len(subgraph["outgoing"]),
            "objects": subgraph["objects"],
        },
    }
    if out:
        written = write_mermaid(Path(out), snapshot=snap)
        result["mermaid_path"] = str(written)
    return result
