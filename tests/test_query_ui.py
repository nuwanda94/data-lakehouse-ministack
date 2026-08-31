from __future__ import annotations

from pathlib import Path

from lakehouse.athena import named_queries
from lakehouse.cli import main
from lakehouse.query_ui import (
    collect_snapshot,
    describe_ui,
    notebook_path,
    render_html,
    write_html,
)


def test_notebook_exists() -> None:
    path = notebook_path()
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "collect_snapshot" in text
    assert "gold_query" in path.name


def test_snapshot_includes_named_queries() -> None:
    snap = collect_snapshot()
    names = {q["name"] for q in snap["named_queries"]}
    expected = {q.name for q in named_queries()}
    assert names == expected
    assert snap["backend"] in {"live", "spec"}


def test_render_html_contains_query_names() -> None:
    snap = {
        "generated_at": "2026-08-31T00:00:00+00:00",
        "backend": "spec",
        "gold_bucket": "lakehouse-local-gold",
        "gold_metrics_table": "lakehouse-local-gold-metrics",
        "pipeline_runs_table": "lakehouse-local-pipeline-runs",
        "gold_objects": ["metrics/dt=2026-08-31/part.json"],
        "metrics": [
            {
                "metric_day": "2026-08-31#purchase",
                "event_type": "purchase",
                "dt": "2026-08-31",
                "events": "3",
                "amount_usd": "12.5",
            }
        ],
        "runs": [{"run_id": "abc", "status": "succeeded", "started_at": "t", "finished_at": "t"}],
        "named_queries": [q.as_dict() for q in named_queries()],
        "errors": [],
    }
    page = render_html(snap)
    assert "gold_daily_totals" in page
    assert "gold_purchase_revenue" in page
    assert "12.5" in page
    assert "abc" in page
    assert "metrics/dt=2026-08-31/part.json" in page


def test_write_html_and_describe(tmp_path: Path) -> None:
    dest = tmp_path / "ui.html"
    written = write_html(dest, snapshot=collect_snapshot())
    assert written.is_file()
    assert "Medallion query UI" in written.read_text(encoding="utf-8")
    result = describe_ui(out=str(tmp_path / "cli.html"))
    assert result["ok"] is True
    assert "gold_daily_totals" in result["named_queries"]
    assert Path(result["html_path"]).is_file()


def test_cli_ui_writes_file(tmp_path: Path, capsys: object) -> None:
    dest = tmp_path / "out.html"
    assert main(["ui", "--out", str(dest)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert dest.is_file()
    assert "gold_daily_totals" in captured.out
    assert '"ok": true' in captured.out
