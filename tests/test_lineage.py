from __future__ import annotations

from pathlib import Path

from lakehouse.cli import main
from lakehouse.lineage import (
    QUARANTINE_NODE_IDS,
    SPEC_EDGES,
    ZONES,
    attach_edge_weights,
    collect_snapshot,
    describe_lineage,
    node_object_counts,
    path_ratio_alert,
    path_ratios,
    quarantine_subgraph,
    render_mermaid,
    spec_graph,
    write_mermaid,
)


def test_spec_graph_covers_medallion_path() -> None:
    graph = spec_graph()
    ids = {n["id"] for n in graph["nodes"]}
    assert ids == {
        "bronze",
        "silver",
        "silver_quarantine",
        "quality",
        "gold",
        "gold_quarantine",
        "runs",
    }
    relations = {(e["from"], e["to"], e["relation"]) for e in graph["edges"]}
    assert relations == set(SPEC_EDGES)
    assert all("weight" in e for e in graph["edges"])
    weights = {(e["from"], e["to"], e["relation"]): e["weight"] for e in graph["edges"]}
    assert weights[("bronze", "silver", "cleanse")] == 18
    assert weights[("bronze", "silver_quarantine", "reject")] == 3
    assert weights[("quality", "gold", "aggregate")] == 1
    assert weights[("quality", "gold_quarantine", "reject")] == 2
    assert weights[("silver_quarantine", "runs", "run_metadata")] == 1
    assert ("bronze", "silver_quarantine", "reject") in relations
    assert ("quality", "silver_quarantine", "quarantine") in relations
    assert graph["ok"] is True
    assert graph["source"] == "spec"
    kinds = {n["id"]: n["kind"] for n in graph["nodes"]}
    assert kinds["silver"] == "cleansed_events"
    assert kinds["silver_quarantine"] == "quality_quarantine"
    subgraph = graph["quarantine_subgraph"]
    assert subgraph["id"] == "quarantine"
    assert subgraph["node_ids"] == list(QUARANTINE_NODE_IDS)
    assert subgraph["objects"] == 5
    assert subgraph["incoming_weight"] == 3 + 3 + 2 + 2
    assert subgraph["outgoing_weight"] == 1 + 1
    ratios = graph["path_ratios"]
    assert ratios["weights"]["cleanse"] == 18 + 1 + 1
    assert ratios["weights"]["reject"] == 3 + 2 + 2
    assert ratios["weights"]["quarantine"] == 3
    assert ratios["total"] == 18 + 1 + 1 + 3 + 2 + 2 + 3
    assert ratios["ratios"]["cleanse"] == 0.6667
    assert ratios["bronze_split"]["weights"] == {"cleanse": 18, "reject": 3}
    assert ratios["quality_split"]["weights"] == {
        "aggregate": 1,
        "reject": 2,
        "quarantine": 3,
    }
    alert = graph["path_ratio_alert"]
    assert alert["metric"] == "cleanse_share"
    assert alert["value"] == 0.6667
    assert alert["floor"] == 0.6
    assert alert["ok"] is True
    assert alert["status"] == "ok"
    page = render_mermaid({"backend": "spec", "spec": graph, "live": None})
    assert "bronze -->|cleanse 18| silver" in page
    assert "quality -->|reject 2| gold_quarantine" in page
    assert "%% path ratios:" in page
    assert "cleanse 0.6667" in page
    assert "%% path-ratio alert: ok cleanse 0.6667 floor 0.6" in page
    incoming = {(e["from"], e["to"], e["relation"]) for e in subgraph["incoming"]}
    assert ("bronze", "silver_quarantine", "reject") in incoming
    assert ("quality", "silver_quarantine", "quarantine") in incoming
    assert ("quality", "gold_quarantine", "reject") in incoming
    assert ("silver", "gold_quarantine", "unreadable") in incoming


def test_snapshot_and_mermaid() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    assert list(snap["zones"]) == list(ZONES)
    page = render_mermaid(snap)
    assert "flowchart LR" in page
    assert "bronze" in page
    assert "gold" in page
    assert "cleanse" in page
    assert "gate" in page
    assert "aggregate" in page
    assert "gold_quarantine" in page
    assert "silver_quarantine" in page
    assert "reject" in page
    assert "quarantine" in page
    assert "unreadable" in page
    assert "subgraph quarantine" in page
    assert "quarantine side paths" in page
    assert "cleanse 18" in page or "cleanse" in page
    assert "|cleanse" in page


def test_write_mermaid_and_describe(tmp_path: Path) -> None:
    dest = tmp_path / "lineage.mmd"
    written = write_mermaid(dest, snapshot=collect_snapshot())
    assert written.is_file()
    result = describe_lineage(out=str(tmp_path / "cli.mmd"))
    assert result["ok"] is True
    assert "bronze" in result["node_ids"]
    assert "gold_quarantine" in result["node_ids"]
    assert "silver_quarantine" in result["node_ids"]
    assert result["edge_count"] == len(SPEC_EDGES)
    assert result["quarantine_subgraph"]["node_ids"] == list(QUARANTINE_NODE_IDS)
    assert result["quarantine_subgraph"]["incoming_count"] == 4
    assert result["quarantine_subgraph"]["outgoing_count"] == 2
    assert "edge_weights" in result
    assert len(result["edge_weights"]) == len(SPEC_EDGES)
    cleanse = next(
        w for w in result["edge_weights"] if w["from"] == "bronze" and w["to"] == "silver"
    )
    assert cleanse["relation"] == "cleanse"
    assert cleanse["weight"] is not None
    assert result["path_ratios"]["ratios"]["cleanse"] is not None
    assert result["path_ratios"]["bronze_split"]["weights"]["cleanse"] is not None
    assert result["path_ratio_alert"]["ok"] is True
    assert result["path_ratio_alert"]["floor"] == 0.6
    assert Path(result["mermaid_path"]).is_file()


def test_quarantine_subgraph_helper() -> None:
    subgraph = quarantine_subgraph(spec_graph())
    assert {n["id"] for n in subgraph["nodes"]} == set(QUARANTINE_NODE_IDS)
    assert subgraph["label"] == "quarantine side paths"


def test_path_ratios_cleanse_reject_quarantine() -> None:
    graph = spec_graph()
    computed = path_ratios(graph)
    family = computed["ratios"]
    assert round(family["cleanse"] + family["reject"] + family["quarantine"], 4) == 1.0
    assert computed["bronze_split"]["ratios"]["cleanse"] == 0.8571
    assert computed["bronze_split"]["ratios"]["reject"] == 0.1429


def test_path_ratio_alert_cleanse_floor() -> None:
    graph = spec_graph()
    green = path_ratio_alert(graph["path_ratios"], cleanse_floor=0.60)
    assert green["ok"] is True
    red = path_ratio_alert(graph["path_ratios"], cleanse_floor=0.80)
    assert red["ok"] is False
    assert red["status"] == "breached"
    assert red["value"] == 0.6667
    assert red["floor"] == 0.8
    assert describe_lineage(cleanse_floor=0.80)["ok"] is False


def test_attach_edge_weights_uses_destination_counts() -> None:
    nodes = [
        {"id": "bronze", "objects": 10},
        {"id": "silver", "objects": 7},
    ]
    edges = attach_edge_weights(
        nodes,
        [{"from": "bronze", "to": "silver", "relation": "cleanse"}],
    )
    assert edges[0]["weight"] == 7
    assert node_object_counts(nodes)["silver"] == 7


def test_cli_lineage(tmp_path: Path, capsys: object) -> None:
    dest = tmp_path / "out.mmd"
    assert main(["lineage", "--out", str(dest)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert dest.is_file()
    assert '"ok": true' in captured.out
    assert "bronze" in captured.out
    assert "path_ratio_alert" in captured.out
    assert "silver_quarantine" in dest.read_text(encoding="utf-8")
    assert main(["lineage", "--cleanse-floor", "0.8"]) == 1
