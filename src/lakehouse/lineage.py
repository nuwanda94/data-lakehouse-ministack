"""Dataset lineage for one medallion run.

MiniStack CI is hermetic, so this module always builds a spec graph
(Bronze raw → Silver cleansed **or** Silver quarantine → quality report →
Gold metrics **or** Gold quarantine rejected-metrics + run row) and
optionally folds in live DynamoDB runs and S3 object counts.

The two quarantine leaves are also exposed as a combined subgraph so
operators can inspect Silver + Gold side paths without walking the
happy-path edges. Edge weights fold into **path ratios**
(cleanse vs reject vs quarantine) plus Bronze and quality cuts.

``python -m lakehouse lineage`` prints JSON. ``--out`` writes Mermaid.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings


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

# Happy-path vs side-path families used for volume ratios.
# ``unreadable`` is a reject-class failure; ``gate``/``aggregate`` stay
# on the cleanse family so operators can read one clean/reject/quarantine
# pie without walking every relation name.
RATIO_FAMILIES: dict[str, tuple[str, ...]] = {
    "cleanse": ("cleanse", "aggregate", "gate"),
    "reject": ("reject", "unreadable"),
    "quarantine": ("quarantine",),
}

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


def node_object_counts(nodes: list[dict[str, Any]]) -> dict[str, int | None]:
    """Map node id → object count (``None`` when the live probe missed)."""

    return {str(n["id"]): n.get("objects") for n in nodes if n.get("id")}


def attach_edge_weights(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stamp each edge with the destination node's live/spec object count.

    Destination weighting matches how operators read a medallion graph:
    ``bronze -->|cleanse| silver`` carries the Silver object volume,
    quarantine rejects carry the quarantine prefix volume, and
    ``run_metadata`` edges carry the sampled run-row count.
    """

    counts = node_object_counts(nodes)
    weighted: list[dict[str, Any]] = []
    for edge in edges:
        dest = edge.get("to")
        weight = counts.get(str(dest)) if dest is not None else None
        if weight is not None:
            try:
                weight = int(weight)
            except (TypeError, ValueError):
                weight = None
        stamped = dict(edge)
        stamped["weight"] = weight
        weighted.append(stamped)
    return weighted


def _edge_weight(edge: dict[str, Any]) -> int:
    raw = edge.get("weight")
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _ratio_map(weights: dict[str, int]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return {key: 0.0 for key in weights}
    return {key: round(value / total, 4) for key, value in weights.items()}


def _family_for(relation: str | None) -> str | None:
    if not relation:
        return None
    for family, relations in RATIO_FAMILIES.items():
        if relation in relations:
            return family
    return None


def path_ratios(graph: dict[str, Any]) -> dict[str, Any]:
    """Share of lineage volume on cleanse vs reject vs quarantine paths.

    Destination weights already live on each edge. This folds them into
    three families (run_metadata is excluded) plus two named cuts:

    * ``bronze_split`` — cleanse vs reject leaving Bronze
    * ``quality_split`` — aggregate vs reject vs quarantine leaving quality
    """

    edges = list(graph.get("edges") or [])
    family_weights = {family: 0 for family in RATIO_FAMILIES}
    for edge in edges:
        family = _family_for(str(edge.get("relation") or ""))
        if family is None:
            continue
        family_weights[family] += _edge_weight(edge)

    bronze_weights = {"cleanse": 0, "reject": 0}
    quality_weights = {"aggregate": 0, "reject": 0, "quarantine": 0}
    for edge in edges:
        relation = str(edge.get("relation") or "")
        weight = _edge_weight(edge)
        if edge.get("from") == "bronze" and relation in bronze_weights:
            bronze_weights[relation] += weight
        if edge.get("from") == "quality" and relation in quality_weights:
            quality_weights[relation] += weight

    total = sum(family_weights.values())
    return {
        "weights": family_weights,
        "total": total,
        "ratios": _ratio_map(family_weights),
        "bronze_split": {
            "weights": bronze_weights,
            "total": sum(bronze_weights.values()),
            "ratios": _ratio_map(bronze_weights),
        },
        "quality_split": {
            "weights": quality_weights,
            "total": sum(quality_weights.values()),
            "ratios": _ratio_map(quality_weights),
        },
    }


def quarantine_subgraph(graph: dict[str, Any]) -> dict[str, Any]:
    """Silver + Gold quarantine leaves as one inspectable subgraph."""

    node_ids = set(QUARANTINE_NODE_IDS)
    nodes = [n for n in graph.get("nodes") or [] if n.get("id") in node_ids]
    incoming = [e for e in graph.get("edges") or [] if e.get("to") in node_ids]
    outgoing = [e for e in graph.get("edges") or [] if e.get("from") in node_ids]
    objects = sum(int(n.get("objects") or 0) for n in nodes)
    incoming_weight = sum(int(e.get("weight") or 0) for e in incoming)
    outgoing_weight = sum(int(e.get("weight") or 0) for e in outgoing)
    return {
        "id": "quarantine",
        "label": "quarantine side paths",
        "node_ids": list(QUARANTINE_NODE_IDS),
        "nodes": nodes,
        "incoming": incoming,
        "outgoing": outgoing,
        "objects": objects,
        "incoming_weight": incoming_weight,
        "outgoing_weight": outgoing_weight,
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
    edges = attach_edge_weights(
        nodes,
        [{"from": src, "to": dst, "relation": rel} for src, dst, rel in SPEC_EDGES],
    )
    graph = {
        "source": "spec",
        "run_id": "spec-run",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "nodes": nodes,
        "edges": edges,
        "ok": True,
    }
    graph["quarantine_subgraph"] = quarantine_subgraph(graph)
    graph["path_ratios"] = path_ratios(graph)
    return graph


def collect_snapshot(settings: Settings | None = None) -> dict[str, Any]:
    from lakehouse.lineage_snapshot import collect_snapshot as _impl

    return _impl(settings)


def render_mermaid(snapshot: dict[str, Any] | None = None) -> str:
    from lakehouse.lineage_render import render_mermaid as _impl

    return _impl(snapshot)


def write_mermaid(path: Path, snapshot: dict[str, Any] | None = None) -> Path:
    from lakehouse.lineage_render import write_mermaid as _impl

    return _impl(path, snapshot)


def describe_lineage(*, out: str | None = None) -> dict[str, Any]:
    from lakehouse.lineage_render import describe_lineage as _impl

    return _impl(out=out)
