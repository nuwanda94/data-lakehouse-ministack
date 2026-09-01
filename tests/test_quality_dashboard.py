from __future__ import annotations

from pathlib import Path

from lakehouse.cli import main
from lakehouse.quality.dashboard import (
    CHECK_NAMES,
    collect_snapshot,
    describe_dashboard,
    render_html,
    spec_summary,
    write_html,
)


def test_spec_summary_covers_named_checks() -> None:
    summary = spec_summary()
    names = {c["check_name"] for c in summary["checks"]}
    assert names == set(CHECK_NAMES)
    assert summary["rows_scanned"] > summary["rows_failed"] > 0
    assert summary["action"] == "quarantine"
    assert summary["passed"] is False
    reasons = {name for row in summary["failed_reasons"] for name in row["reasons"]}
    assert "event_id_present" in reasons
    assert "known_event_type" in reasons
    assert "quantity_and_amount_sane" in reasons


def test_snapshot_and_html() -> None:
    snap = collect_snapshot()
    assert snap["backend"] in {"live", "spec"}
    assert snap["spec"]["checks"]
    page = render_html(snap)
    assert "Medallion quality dashboard" in page
    assert "event_id_present" in page
    assert "known_event_type" in page


def test_write_html_and_describe(tmp_path: Path) -> None:
    dest = tmp_path / "quality.html"
    written = write_html(dest, snapshot=collect_snapshot())
    assert written.is_file()
    result = describe_dashboard(out=str(tmp_path / "cli.html"))
    assert result["ok"] is True
    assert "event_id_present" in result["check_names"]
    assert Path(result["html_path"]).is_file()


def test_cli_quality_dashboard(tmp_path: Path, capsys: object) -> None:
    dest = tmp_path / "out.html"
    assert main(["quality-dashboard", "--out", str(dest)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert dest.is_file()
    assert "event_id_present" in captured.out
    assert '"ok": true' in captured.out
