"""Hermetic release plan: version + CHANGELOG + optional git tag.

The unit suite never creates tags. `python -m lakehouse release` prints a JSON
plan. `make tag VERSION=0.1.0` is the explicit path that writes an annotated
`vX.Y.Z` tag after the plan is clean.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HEADING_RE = re.compile(r"^## \[([^\]]+)\](?:\s+-\s+(\S+))?")
VERSION_RE = re.compile(r"^version\s*=\s*\"([^\"]+)\"\s*$", re.MULTILINE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "CHANGELOG.md").is_file():
            return parent
        if (parent / "pyproject.toml").is_file() and (parent / "infra").is_dir():
            return parent
    return Path.cwd()


def read_pyproject_version(root: Path | None = None) -> str:
    root = root or repo_root()
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("pyproject.toml is missing project.version")
    return match.group(1)


def read_package_version() -> str:
    from lakehouse import __version__

    return __version__


@dataclass(frozen=True)
class ChangelogSection:
    title: str
    date: str | None
    body: str

    @property
    def is_unreleased(self) -> bool:
        return self.title.lower() == "unreleased"


def parse_changelog(text: str) -> list[ChangelogSection]:
    lines = text.splitlines()
    headings: list[tuple[int, str, str | None]] = []
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if match:
            headings.append((idx, match.group(1), match.group(2)))
    sections: list[ChangelogSection] = []
    for i, (start, title, date) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip()
        sections.append(ChangelogSection(title=title, date=date, body=body))
    return sections


def changelog_versions(sections: list[ChangelogSection]) -> list[str]:
    return [s.title for s in sections if not s.is_unreleased]


@dataclass
class ReleasePlan:
    version: str
    tag: str
    ok: bool
    pyproject_version: str
    package_version: str
    changelog_has_version: bool
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    changelog_headings: list[str] = field(default_factory=list)
    existing_tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "version": self.version,
            "tag": self.tag,
            "pyproject_version": self.pyproject_version,
            "package_version": self.package_version,
            "changelog_has_version": self.changelog_has_version,
            "errors": self.errors,
            "notes": self.notes,
            "changelog_headings": self.changelog_headings,
            "existing_tags": self.existing_tags,
        }


def _git_tags(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "tag", "--list", "v*"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def plan_release(root: Path | None = None, *, version: str | None = None) -> ReleasePlan:
    root = root or repo_root()
    py_version = read_pyproject_version(root)
    pkg_version = read_package_version()
    requested = version or py_version
    changelog_path = root / "CHANGELOG.md"
    if changelog_path.is_file():
        sections = parse_changelog(changelog_path.read_text(encoding="utf-8"))
    else:
        sections = []
    headings = [s.title for s in sections]
    has_version = any(s.title == requested and not s.is_unreleased for s in sections)
    errors: list[str] = []
    notes: list[str] = []

    if not SEMVER_RE.match(requested):
        errors.append(f"version {requested!r} is not semver X.Y.Z")
    if py_version != pkg_version:
        errors.append(
            f"pyproject version {py_version} != lakehouse.__version__ {pkg_version}"
        )
    if requested != py_version:
        errors.append(f"requested version {requested} != pyproject {py_version}")
    if not changelog_path.is_file():
        errors.append("CHANGELOG.md is missing")
    elif not has_version:
        errors.append(f"CHANGELOG.md has no '## [{requested}]' section")
    else:
        section = next(s for s in sections if s.title == requested)
        if not section.body:
            errors.append(f"CHANGELOG section [{requested}] is empty")

    tags = _git_tags(root)
    tag = f"v{requested}"
    if tag in tags:
        notes.append(f"git tag {tag} already exists")

    return ReleasePlan(
        version=requested,
        tag=tag,
        ok=not errors,
        pyproject_version=py_version,
        package_version=pkg_version,
        changelog_has_version=has_version,
        errors=errors,
        notes=notes,
        changelog_headings=headings,
        existing_tags=tags,
    )


def create_annotated_tag(
    root: Path | None = None,
    *,
    version: str | None = None,
    dry_run: bool = True,
) -> dict[str, object]:
    """Create `vX.Y.Z` only when the plan is clean and dry_run is False."""
    root = root or repo_root()
    plan = plan_release(root, version=version)
    payload = plan.as_dict()
    payload["dry_run"] = dry_run
    payload["tagged"] = False
    if not plan.ok:
        return payload
    if plan.tag in plan.existing_tags:
        payload["tagged"] = True
        payload["notes"] = list(plan.notes) + [f"left existing {plan.tag} in place"]
        return payload
    if dry_run:
        payload["notes"] = list(plan.notes) + [f"would create annotated tag {plan.tag}"]
        return payload
    message = f"Release {plan.tag}"
    proc = subprocess.run(
        ["git", "tag", "-a", plan.tag, "-m", message],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    payload["git_returncode"] = proc.returncode
    payload["git_stderr"] = proc.stderr.strip()
    payload["tagged"] = proc.returncode == 0
    if proc.returncode != 0:
        payload["ok"] = False
        payload["errors"] = list(plan.errors) + [proc.stderr.strip() or "git tag failed"]
    return payload
