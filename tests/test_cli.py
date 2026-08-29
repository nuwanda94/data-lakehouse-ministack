from __future__ import annotations

from lakehouse.cli import main


def test_version(capsys: object) -> None:
    assert main(["--version"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out.strip() == "0.1.0"


def test_settings_json(capsys: object, monkeypatch: object) -> None:
    monkeypatch.setenv("GOLD_BUCKET", "g-test")  # type: ignore[attr-defined]
    assert main(["settings"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "g-test" in captured.out


def test_outputs_defaults_json(tmp_path, capsys: object) -> None:
    empty = tmp_path / "tf"
    empty.mkdir()
    assert main(["outputs", "--tf-dir", str(empty), "--json"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "lakehouse-local-bronze" in captured.out


def test_sfn_def_prints_asl(capsys: object) -> None:
    assert main(["sfn-def"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "IngestBronze" in captured.out
    assert "QualityChoice" in captured.out
    assert "AggregateGold" in captured.out
