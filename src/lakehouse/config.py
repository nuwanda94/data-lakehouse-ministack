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
    "BRONZE_EVENTS_QUEUE": "lakehouse-local-bronze-events",
    "BRONZE_EVENTS_QUEUE_URL": "",
    "LOG_LEVEL": "INFO",
    "PROJECT": "lakehouse",
    "ENV": "local",
}

_LINE_RE = re.compile(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def load_env_file(
    path: str | Path | None = None,
    *,
    override: bool = False,
) -> dict[str, str]:
    """Parse a dotenv file and merge into ``os.environ``.

    Returns the key/value pairs that were applied (or skipped when already set).
    """
    if path is None:
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ]
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
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        key, value = m.group("key"), _strip_quotes(m.group("value").strip())
        if override or key not in os.environ:
            os.environ[key] = value
        applied[key] = value
    return applied


@dataclass(frozen=True, slots=True)
class Settings:
    endpoint_url: str
    region: str
    access_key_id: str
    secret_access_key: str
    bronze_bucket: str
    silver_bucket: str
    gold_bucket: str
    pipeline_runs_table: str
    gold_metrics_table: str
    bronze_events_queue: str
    bronze_events_queue_url: str
    log_level: str
    project: str
    env: str

    @property
    def prefix(self) -> str:
        return f"{self.project}-{self.env}"


def _get(name: str, defaults: dict[str, str] | None = None) -> str:
    defaults = defaults or _DEFAULTS
    return os.environ.get(name) or defaults.get(name, "")


def get_settings(*, load_env_file: bool = True) -> Settings:
    if load_env_file:
        globals()["load_env_file"]()
    return Settings(
        endpoint_url=_get("AWS_ENDPOINT_URL"),
        region=_get("AWS_DEFAULT_REGION"),
        access_key_id=_get("AWS_ACCESS_KEY_ID"),
        secret_access_key=_get("AWS_SECRET_ACCESS_KEY"),
        bronze_bucket=_get("BRONZE_BUCKET"),
        silver_bucket=_get("SILVER_BUCKET"),
        gold_bucket=_get("GOLD_BUCKET"),
        pipeline_runs_table=_get("PIPELINE_RUNS_TABLE"),
        gold_metrics_table=_get("GOLD_METRICS_TABLE"),
        bronze_events_queue=_get("BRONZE_EVENTS_QUEUE"),
        bronze_events_queue_url=_get("BRONZE_EVENTS_QUEUE_URL"),
        log_level=_get("LOG_LEVEL"),
        project=_get("PROJECT"),
        env=_get("ENV"),
    )
