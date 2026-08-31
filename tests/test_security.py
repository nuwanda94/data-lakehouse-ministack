from __future__ import annotations

from pathlib import Path

from lakehouse.cli import main
from lakehouse.security import scan_repo, scan_text


def test_dummy_ministack_secret_is_allowed() -> None:
    text = "AWS_SECRET_ACCESS_KEY=test\nAWS_ACCESS_KEY_ID=test\n"
    assert scan_text(text, relpath=".env.example") == []


def test_real_looking_akia_is_flagged() -> None:
    text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
    hits = scan_text(text, relpath="leak.env")
    assert any(h.kind == "aws_access_key_id" for h in hits)


def test_pem_private_key_is_flagged() -> None:
    text = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
    hits = scan_text(text, relpath="id_rsa")
    assert any(h.kind == "private_key" for h in hits)


def test_repo_scan_is_clean() -> None:
    report = scan_repo()
    assert report.config_ok, report.notes
    assert report.findings == [], report.findings
    assert report.ok
    assert report.files_scanned > 20
    root = Path(__file__).resolve().parents[1]
    assert (root / ".checkov.yaml").is_file()
    assert (root / "trivy.yaml").is_file()


def test_cli_security_ok(capsys: object) -> None:
    assert main(["security"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"ok": true' in captured.out
