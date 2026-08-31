from __future__ import annotations

from pathlib import Path

from lakehouse.release import (
    create_annotated_tag,
    parse_changelog,
    plan_release,
    read_package_version,
    read_pyproject_version,
    repo_root,
)


CHANGELOG = """# Changelog

## [Unreleased]

- pending

## [0.1.0] - 2026-09-01

- shipped
"""


def test_parse_changelog_sections() -> None:
    sections = parse_changelog(CHANGELOG)
    assert [s.title for s in sections] == ["Unreleased", "0.1.0"]
    assert sections[0].is_unreleased
    assert sections[1].date == "2026-09-01"
    assert "shipped" in sections[1].body


def test_plan_matches_package_version() -> None:
    root = repo_root()
    plan = plan_release(root)
    assert plan.pyproject_version == read_pyproject_version(root)
    assert plan.package_version == read_package_version()
    assert plan.version == plan.pyproject_version
    assert plan.tag == f"v{plan.version}"
    assert plan.ok, plan.errors
    assert plan.changelog_has_version


def test_plan_rejects_unknown_version(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('version = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (tmp_path / "infra").mkdir()
    plan = plan_release(tmp_path, version="9.9.9")
    assert not plan.ok
    assert any("9.9.9" in err for err in plan.errors)


def test_dry_run_tag_does_not_fail_when_plan_ok() -> None:
    payload = create_annotated_tag(dry_run=True)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["tagged"] is False
    notes = " ".join(str(n) for n in payload["notes"])
    assert "would create" in notes or "already exists" in notes


def test_plan_dict_has_tag() -> None:
    payload = plan_release().as_dict()
    assert payload["ok"] is True
    assert payload["tag"] == "v0.1.0"
    assert payload["version"] == "0.1.0"
