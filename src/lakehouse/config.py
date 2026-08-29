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
    "BRONZE_EVENTS_DLQ": "lakehouse-local-bronze-events-dlq",
    "BRONZE_EVENTS_DLQ_URL": "",
}

_LINE_RE = re.compile(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$")


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
    resolved: Path | None
    if path is not None:
        resolved = Path(path)
        if not resolved.is_file():
            return None
    elif search:
        resolved = find_env_file()
        if resolved is None:
            return None
    else:
        return None

    for key, value in parse_dotenv(resolved.read_text(encoding="utf-8")).items():
        if override or key not in os.environ:
            os.environ[key] = value
    return resolved


def _require(name: str, value: str | None) -> str:
    if value is None or value == "":
        raise ValueError(f"{name} must be set (empty values are not allowed)")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    aws_endpoint_url: str
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    bronze_bucket: str
    silver_bucket: str
    gold_bucket: str
    pipeline_runs_table: str
    gold_metrics_table: str
    bronze_events_queue: str
    bronze_events_queue_url: str
    bronze_events_dlq: str = "lakehouse-local-bronze-events-dlq"
    bronze_events_dlq_url: str = ""

    @property
    def buckets(self) -> tuple[str, str, str]:
        return (self.bronze_bucket, self.silver_bucket, self.gold_bucket)


def load_settings(
    *,
    load_env_file: bool = True,
    env_file: str | Path | None = None,
) -> Settings:
    """Build Settings from the environment.

    When ``load_env_file`` is True, a discovered ``.env`` is applied first
    (without overriding already-set process env vars). Pass ``env_file`` to
    load a specific path instead of searching.
    """
    if env_file is not None:
        load_dotenv(env_file, search=False)
    elif load_env_file:
        load_dotenv()

    return Settings(
        aws_endpoint_url=_require(
            "AWS_ENDPOINT_URL", os.environ.get("AWS_ENDPOINT_URL", _DEFAULTS["AWS_ENDPOINT_URL"])
        ),
        aws_region=_require(
            "AWS_DEFAULT_REGION",
            os.environ.get("AWS_DEFAULT_REGION", _DEFAULTS["AWS_DEFAULT_REGION"]),
        ),
        aws_access_key_id=_require(
            "AWS_ACCESS_KEY_ID",
            os.environ.get("AWS_ACCESS_KEY_ID", _DEFAULTS["AWS_ACCESS_KEY_ID"]),
        ),
        aws_secret_access_key=_require(
            "AWS_SECRET_ACCESS_KEY",
            os.environ.get("AWS_SECRET_ACCESS_KEY", _DEFAULTS["AWS_SECRET_ACCESS_KEY"]),
        ),
        bronze_bucket=_require(
            "BRONZE_BUCKET", os.environ.get("BRONZE_BUCKET", _DEFAULTS["BRONZE_BUCKET"])
        ),
        silver_bucket=_require(
            "SILVER_BUCKET", os.environ.get("SILVER_BUCKET", _DEFAULTS["SILVER_BUCKET"])
        ),
        gold_bucket=_require(
            "GOLD_BUCKET", os.environ.get("GOLD_BUCKET", _DEFAULTS["GOLD_BUCKET"])
        ),
        pipeline_runs_table=_require(
            "PIPELINE_RUNS_TABLE",
            os.environ.get("PIPELINE_RUNS_TABLE", _DEFAULTS["PIPELINE_RUNS_TABLE"]),
        ),
        gold_metrics_table=_require(
            "GOLD_METRICS_TABLE",
            os.environ.get("GOLD_METRICS_TABLE", _DEFAULTS["GOLD_METRICS_TABLE"]),
        ),
        bronze_events_queue=_require(
            "BRONZE_EVENTS_QUEUE",
            os.environ.get("BRONZE_EVENTS_QUEUE", _DEFAULTS["BRONZE_EVENTS_QUEUE"]),
        ),
        bronze_events_queue_url=os.environ.get(
            "BRONZE_EVENTS_QUEUE_URL", _DEFAULTS["BRONZE_EVENTS_QUEUE_URL"]
        )
        or "",
        bronze_events_dlq=_require(
            "BRONZE_EVENTS_DLQ",
            os.environ.get("BRONZE_EVENTS_DLQ", _DEFAULTS["BRONZE_EVENTS_DLQ"]),
        ),
        bronze_events_dlq_url=os.environ.get(
            "BRONZE_EVENTS_DLQ_URL", _DEFAULTS["BRONZE_EVENTS_DLQ_URL"]
        )
        or "",
    )


get_settings = load_settings
