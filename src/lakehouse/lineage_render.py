"""Mermaid + CLI describe helpers for lineage path ratios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lakehouse.lineage import (
    QUARANTINE_NODE_IDS,
    RATIO_FAMILIES,
    path_ratio_alert,
    path_ratios,
    quarantine_subgraph,
)
from lakehouse.lineage_snapshot import collect_snapshot


def render_mermaid(snapshot: dict[str, Any] | None = None) -> str:
    """Render a flowchart that reviewers can paste into GitHub / Mermaid."""

    snap = snapshot or collect_snapshot()
    graph = snap["live"] if snap.get("backend") == "live" else snap["spec"]
    ratios = graph.get("path_ratios") or snap.get("path_ratios") or path_ratios(graph)
    family = ratios.get("ratios") or {}
    alert = (
        graph.get("path_ratio_alert") or snap.get("path_ratio_alert") or path_ratio_alert(ratios)
    )
    q_ids = set(QUARANTINE_NODE_IDS)
    lines = ["flowchart LR"]
    if family:
        parts = " ".join(f"{name} {family[name]}" for name in RATIO_FAMILIES if name in family)
        lines.append(f"  %% path ratios: {parts}")
    bronze_cut = (alert.get("cuts") or {}).get("bronze_split") or {}
    lines.append(
        "  %% path-ratio alert: "
        f"{alert.get('status')} cleanse {alert.get('value')} floor {alert.get('floor')}"
    )
    lines.append(
        "  %% bronze-split alert: "
        f"{'ok' if bronze_cut.get('ok', True) else 'breached'} "
        f"cleanse {bronze_cut.get('value')} floor {bronze_cut.get('floor')}"
    )
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
        label = str(edge["relation"])
        weight = edge.get("weight")
        if weight is not None:
            label = f"{label} {weight}"
        lines.append(f"  {edge['from']} -->|{label}| {edge['to']}")
    return "\n".join(lines) + "\n"


def write_mermaid(path: Path, snapshot: dict[str, Any] | None = None) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_mermaid(snapshot), encoding="utf-8")
    return dest


def describe_lineage(
    *,
    out: str | None = None,
    cleanse_floor: float | None = None,
    bronze_cleanse_floor: float | None = None,
) -> dict[str, Any]:
    snap = collect_snapshot()
    graph = snap["live"] if snap["backend"] == "live" else snap["spec"]
    subgraph = snap.get("quarantine_subgraph") or quarantine_subgraph(graph)
    ratios = graph.get("path_ratios") or snap.get("path_ratios") or path_ratios(graph)
    alert = path_ratio_alert(
        ratios,
        cleanse_floor=cleanse_floor,
        bronze_cleanse_floor=bronze_cleanse_floor,
    )
    result: dict[str, Any] = {
        "ok": bool(alert["ok"]),
        "backend": snap["backend"],
        "run_id": graph.get("run_id"),
        "node_ids": [n["id"] for n in graph["nodes"]],
        "edge_count": len(graph["edges"]),
        "zones": snap["zones"],
        "edge_weights": [
            {
                "from": e["from"],
                "to": e["to"],
                "relation": e["relation"],
                "weight": e.get("weight"),
            }
            for e in graph["edges"]
        ],
        "quarantine_subgraph": {
            "id": subgraph["id"],
            "label": subgraph["label"],
            "node_ids": subgraph["node_ids"],
            "incoming_count": len(subgraph["incoming"]),
            "outgoing_count": len(subgraph["outgoing"]),
            "objects": subgraph["objects"],
            "incoming_weight": subgraph.get("incoming_weight"),
            "outgoing_weight": subgraph.get("outgoing_weight"),
        },
        "path_ratios": {
            "weights": ratios.get("weights"),
            "total": ratios.get("total"),
            "ratios": ratios.get("ratios"),
            "bronze_split": ratios.get("bronze_split"),
            "quality_split": ratios.get("quality_split"),
        },
        "path_ratio_alert": alert,
    }
    if out:
        written = write_mermaid(Path(out), snapshot=snap)
        result["mermaid_path"] = str(written)
    return result
