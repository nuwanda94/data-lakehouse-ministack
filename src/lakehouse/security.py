"""Hermetic secret + scanner-config checks (no Checkov/Trivy required)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".terraform",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    ".ministack",
}

SKIP_FILE_NAMES = {
    ".secrets.baseline",
    "PROGRESS.md",
    "TODO.md",
}

# Dummy MiniStack credentials from .env.example — never treat as findings.
ALLOWED_SECRET_VALUES = {"test", "testing", "changeme", "dummy"}

AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
PEM_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")
GITHUB_PAT = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")
GITHUB_FINEGRAIN = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")
SLACK_TOKEN = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
AWS_SECRET_ASSIGN = re.compile(
    r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{20,})['\"]?"
)
GENERIC_KEY_ASSIGN = re.compile(
    r"(?i)(?:api_key|apikey|secret_key)\s*[=:]\s*['\"]([A-Za-z0-9/+=_-]{24,})['\"]"
)

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key_id", AWS_ACCESS_KEY),
    ("private_key", PEM_PRIVATE_KEY),
    ("github_token", GITHUB_PAT),
    ("github_pat", GITHUB_FINEGRAIN),
    ("slack_token", SLACK_TOKEN),
    ("aws_secret_access_key", AWS_SECRET_ASSIGN),
    ("generic_api_key", GENERIC_KEY_ASSIGN),
)


@dataclass
class Finding:
    path: str
    line: int
    kind: str
    excerpt: str


@dataclass
class SecurityReport:
    ok: bool
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    config_ok: bool = True
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "files_scanned": self.files_scanned,
            "findings": [
                {
                    "path": f.path,
                    "line": f.line,
                    "kind": f.kind,
                    "excerpt": f.excerpt,
                }
                for f in self.findings
            ],
            "config_ok": self.config_ok,
            "notes": self.notes,
        }


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "infra").is_dir():
            return parent
    return Path.cwd()


def _is_skipped_dir(path: Path) -> bool:
    return path.name in SKIP_DIR_NAMES


def iter_text_files(root: Path | None = None) -> list[Path]:
    root = root or repo_root()
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(_is_skipped_dir(part) for part in path.relative_to(root).parents):
            continue
        if path.name in SKIP_FILE_NAMES:
            continue
        if path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".zip",
            ".pyc",
            ".so",
            ".whl",
        }:
            continue
        out.append(path)
    return sorted(out)


def _allowed_assignment(match: re.Match[str]) -> bool:
    if match.lastindex:
        value = match.group(1).strip().strip("'\"")
        return value.lower() in ALLOWED_SECRET_VALUES
    return False


def scan_text(text: str, *, relpath: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(line):
                if kind in {"aws_secret_access_key", "generic_api_key"} and _allowed_assignment(
                    match
                ):
                    continue
                findings.append(
                    Finding(
                        path=relpath,
                        line=lineno,
                        kind=kind,
                        excerpt=line.strip()[:120],
                    )
                )
    return findings


def required_config_files(root: Path | None = None) -> list[Path]:
    root = root or repo_root()
    return [
        root / ".checkov.yaml",
        root / "trivy.yaml",
        root / ".trivyignore",
        root / "docs" / "security.md",
    ]


def scan_repo(root: Path | None = None) -> SecurityReport:
    root = root or repo_root()
    report = SecurityReport(ok=True)
    missing = [p for p in required_config_files(root) if not p.is_file()]
    if missing:
        report.config_ok = False
        report.ok = False
        report.notes.append("missing scanner config: " + ", ".join(str(p.name) for p in missing))
    for path in iter_text_files(root):
        report.files_scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report.notes.append(f"skip unreadable {path}: {exc}")
            continue
        rel = str(path.relative_to(root))
        report.findings.extend(scan_text(text, relpath=rel))
    if report.findings:
        report.ok = False
    return report
