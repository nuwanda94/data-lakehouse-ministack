from __future__ import annotations

from pathlib import Path

from lakehouse.cli import main
from lakehouse.lineage import (
    SPEC_EDGES,
    ZONES,
    collect_snapshot,
    describe_lineage,
    render_mermaid,
    spec_graph,
    write_mermaid,
)


def test_spec_graph_covers_medallion_path() -> None:
    graph = spec_graph()
    ids = {n["id"] for n in graph["nodes"]}
    assert ids == {"bronze", "silver", "quality", "gold", "runs"}
    relations = {(e["from"], e["to"], e["relation"]) for e in graph["edges"]}
    assert relations == set(SPEC_EDGES)
    assert graph["ok"] is True
    assert graph["source"] == "spec"


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


def test_write_mermaid_and_describe(tmp_path: Path) -> None:
    dest = tmp_path / "lineage.mmd"
    written = write_mermaid(dest, snapshot=collect_snapshot())
    assert written.is_file()
    result = describe_lineage(out=str(tmp_path / "cli.mmd"))
    assert result["ok"] is True
    assert "bronze" in result["node_ids"]
    assert result["edge_count"] == len(SPEC_EDGES)
    assert Path(result["mermaid_path"]).is_file()


def test_cli_lineage(tmp_path: Path, capsys: object) -> None:
    dest = tmp_path / "out.mmd"
    assert main(["lineage", "--out", str(dest)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert dest.is_file()
    assert '"ok": true' in captured.out
    assert "bronze" in captured.out
