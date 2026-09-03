from __future__ import annotations

from pathlib import Path

from lakehouse.cli import main
from lakehouse.lineage import (
    QUARANTINE_NODE_IDS,
    SPEC_EDGES,
    ZONES,
    collect_snapshot,
    describe_lineage,
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
    assert Path(result["mermaid_path"]).is_file()


def test_quarantine_subgraph_helper() -> None:
    subgraph = quarantine_subgraph(spec_graph())
    assert {n["id"] for n in subgraph["nodes"]} == set(QUARANTINE_NODE_IDS)
    assert subgraph["label"] == "quarantine side paths"


def test_cli_lineage(tmp_path: Path, capsys: object) -> None:
    dest = tmp_path / "out.mmd"
    assert main(["lineage", "--out", str(dest)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert dest.is_file()
    assert '"ok": true' in captured.out
    assert "bronze" in captured.out
    assert "silver_quarantine" in dest.read_text(encoding="utf-8")
