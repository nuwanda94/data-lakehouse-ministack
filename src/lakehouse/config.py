"""Runtime configuration for the lakehouse package."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

_LINE_RE = re.compile(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$")


def _strip_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def load_env_file(path: Path | str | None = None, *, override: bool = False) -> dict[str, str]:
    """Load KEY=VALUE pairs from a dotenv-style file into os.environ.

    Returns the pairs that were applied (or would have been if override=False
    and the key already existed).
    """
    if path is None:
        candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
        for candidate in candidates:
            if candidate.is_file():
                path = candidate
                break
        else:
            return {}

    path = Path(path)
    if not path.is_file():
        return {}

    applied: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        value = _strip_value(match.group("value"))
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable view of process configuration."""

    endpoint_url: str
    region: str
    project: str
    env: str
    bronze_bucket: str
    silver_bucket: str
    gold_bucket: str
    runs_table: str
    metrics_table: str
    bronze_queue_url: str | None
    log_level: str

    @property
    def bucket_prefix(self) -> str:
        return f"{self.project}-{self.env}"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def get_settings(*, load_dotenv: bool = True) -> Settings:
    """Build Settings from the environment (optionally loading .env first)."""
    if load_dotenv:
        load_env_file()

    project = _env("LAKEHOUSE_PROJECT", "lakehouse") or "lakehouse"
    env_name = _env("LAKEHOUSE_ENV", "local") or "local"
    prefix = f"{project}-{env_name}"

    return Settings(
        endpoint_url=_env("AWS_ENDPOINT_URL", "http://localhost:4566") or "http://localhost:4566",
        region=_env("AWS_DEFAULT_REGION", "us-east-1") or "us-east-1",
        project=project,
        env=env_name,
        bronze_bucket=_env("LAKEHOUSE_BRONZE_BUCKET", f"{prefix}-bronze") or f"{prefix}-bronze",
        silver_bucket=_env("LAKEHOUSE_SILVER_BUCKET", f"{prefix}-silver") or f"{prefix}-silver",
        gold_bucket=_env("LAKEHOUSE_GOLD_BUCKET", f"{prefix}-gold") or f"{prefix}-gold",
        runs_table=_env("LAKEHOUSE_RUNS_TABLE", f"{prefix}-runs") or f"{prefix}-runs",
        metrics_table=_env("LAKEHOUSE_METRICS_TABLE", f"{prefix}-metrics") or f"{prefix}-metrics",
        bronze_queue_url=_env("LAKEHOUSE_BRONZE_QUEUE_URL"),
        log_level=_env("LOG_LEVEL", "INFO") or "INFO",
    )


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Cached settings for the process lifetime."""
    return get_settings()
