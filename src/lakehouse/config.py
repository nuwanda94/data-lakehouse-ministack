"""Runtime settings loaded from process environment and optional `.env` files.

Precedence (highest first):
1. Existing process environment variables
2. Values from a discovered or explicit `.env` file
3. Documented defaults in `_DEFAULTS`

`.env` loading never overrides variables that are already set. That keeps
Makefile / Terraform output injection (`scripts/tf_env.sh`) authoritative.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_DEFAULTS = {
    "AWS_ENDPOINT_URL": "http://localhost:4566",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "BRONZE_BUCKET": "lakehouse-local-bronze",
    "SILVER_BUCKET": "lakehouse-local-silver",
    "GOLD_BUCKET": "lakehouse-local-gold",
    "PIPELINE_RUNS_TABLE": "lakehouse-local-pipeline-runs",
    "GOLD_METRICS_TABLE": "lakehouse-local-gold-metrics",
}

_LINE_RE = re.compile(
    r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$"
)


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse a subset of dotenv syntax used by this project."""

    parsed: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match is None:
            continue
        value = match.group("value").strip()
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        parsed[match.group("key")] = value
    return parsed


def find_env_file(
    start: Path | None = None,
    filename: str = ".env",
) -> Path | None:
    """Walk upward from ``start`` (default: cwd) looking for ``filename``."""

    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        path = candidate / filename
        if path.is_file():
            return path
    return None


def load_dotenv(
    path: str | Path | None = None,
    *,
    override: bool = False,
    search: bool = True,
) -> Path | None:
    """Load KEY=VALUE pairs into ``os.environ``.

    Returns the path that was loaded, or ``None`` if nothing was found.
    """

    env_path: Path | None
    if path is not None:
        env_path = Path(path)
        if not env_path.is_file():
            return None
    elif search:
        env_path = find_env_file()
    else:
        return None

    if env_path is None:
        return None

    values = parse_dotenv(env_path.read_text(encoding="utf-8"))
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return env_path


def _env(name: str) -> str:
    value = os.environ.get(name, _DEFAULTS[name])
    if not value:
        raise ValueError(f"Required setting {name} is empty")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Typed view of lakehouse + MiniStack connection settings."""

    aws_endpoint_url: str
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    bronze_bucket: str
    silver_bucket: str
    gold_bucket: str
    pipeline_runs_table: str
    gold_metrics_table: str

    @property
    def buckets(self) -> tuple[str, str, str]:
        return (self.bronze_bucket, self.silver_bucket, self.gold_bucket)


def load_settings(
    *,
    env_file: str | Path | None = None,
    load_env_file: bool = True,
) -> Settings:
    """Build settings from process env, optional `.env`, then defaults."""

    if load_env_file:
        load_dotenv(path=env_file, override=False, search=env_file is None)

    return Settings(
        aws_endpoint_url=_env("AWS_ENDPOINT_URL"),
        aws_region=_env("AWS_DEFAULT_REGION"),
        aws_access_key_id=_env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("AWS_SECRET_ACCESS_KEY"),
        bronze_bucket=_env("BRONZE_BUCKET"),
        silver_bucket=_env("SILVER_BUCKET"),
        gold_bucket=_env("GOLD_BUCKET"),
        pipeline_runs_table=_env("PIPELINE_RUNS_TABLE"),
        gold_metrics_table=_env("GOLD_METRICS_TABLE"),
    )


get_settings = load_settings
