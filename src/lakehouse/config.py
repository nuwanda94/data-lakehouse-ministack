"""Runtime settings loaded from env, optional config file, and optional SSM.

Precedence (highest first):
1. Existing process environment variables
2. SSM parameter JSON when ``SSM_ENABLED`` / ``features.ssm`` is on
3. ``configs/pipeline.json`` (or ``LAKEHOUSE_CONFIG``)
4. Values from a discovered or explicit ``.env`` file (never overrides env)
5. Documented defaults in ``_DEFAULTS``

``.env`` loading never overrides variables that are already set. That keeps
Makefile / Terraform output injection (``scripts/tf_env.sh``) authoritative.
The checked-in config file holds *behavior* knobs (quality, lookback,
partitions, feature flags), not bucket names.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
    "LOOKBACK_DAYS": "2",
    "QUALITY_ON_FAIL": "fail",
    "QUALITY_MAX_FAIL_RATIO": "0.0",
    "PARTITION_STRATEGY": "hive",
    "BRONZE_PREFIX": "events/",
    "SILVER_PREFIX": "events/",
    "GOLD_PREFIX": "metrics/",
    "FEATURE_SFN": "true",
    "FEATURE_EMIT_METRICS": "false",
    "SSM_ENABLED": "false",
    "CONFIG_SSM_PARAMETER": "/lakehouse-local/pipeline",
}

_LINE_RE = re.compile(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$")
_TRUTHY = {"1", "true", "yes", "on"}
_VALID_ON_FAIL = {"fail", "quarantine"}
_VALID_PARTITION = {"hive", "date_prefix"}


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
    """Walk upward from ``start`` (default: cwd) looking for ``filename`."""

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


def _as_bool(raw: str | bool | None, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in _TRUTHY


def _as_float(raw: str | float | int | None, default: float = 0.0) -> float:
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value < 0:
        return default
    return value


def _as_on_fail(raw: str | None, default: str = "fail") -> str:
    if raw is None or raw == "":
        return default
    value = str(raw).strip().lower()
    return value if value in _VALID_ON_FAIL else default


def _as_partition(raw: str | None, default: str = "hive") -> str:
    if raw is None or raw == "":
        return default
    value = str(raw).strip().lower()
    return value if value in _VALID_PARTITION else default


def find_pipeline_config(
    start: Path | None = None,
    filename: str = "pipeline.json",
) -> Path | None:
    """Locate ``configs/pipeline.json`` from cwd, package, or parents."""

    explicit = os.environ.get("LAKEHOUSE_CONFIG")
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None

    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        path = candidate / "configs" / filename
        if path.is_file():
            return path

    pkg_root = Path(__file__).resolve().parents[2]
    packaged = pkg_root / "configs" / filename
    if packaged.is_file():
        return packaged
    return None


def parse_pipeline_config(payload: dict[str, Any]) -> dict[str, str]:
    """Flatten ``configs/pipeline.json`` into env-style keys."""

    flat: dict[str, str] = {}
    if "lookback_days" in payload and payload["lookback_days"] is not None:
        flat["LOOKBACK_DAYS"] = str(payload["lookback_days"])

    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    if "on_fail" in quality and quality["on_fail"] is not None:
        flat["QUALITY_ON_FAIL"] = str(quality["on_fail"])
    if "max_fail_ratio" in quality and quality["max_fail_ratio"] is not None:
        flat["QUALITY_MAX_FAIL_RATIO"] = str(quality["max_fail_ratio"])

    partitions = payload.get("partitions") if isinstance(payload.get("partitions"), dict) else {}
    if partitions.get("strategy"):
        flat["PARTITION_STRATEGY"] = str(partitions["strategy"])
    if partitions.get("bronze_prefix"):
        flat["BRONZE_PREFIX"] = str(partitions["bronze_prefix"])
    if partitions.get("silver_prefix"):
        flat["SILVER_PREFIX"] = str(partitions["silver_prefix"])
    if partitions.get("gold_prefix"):
        flat["GOLD_PREFIX"] = str(partitions["gold_prefix"])

    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    if "sfn" in features:
        flat["FEATURE_SFN"] = "true" if _as_bool(features["sfn"]) else "false"
    if "emit_metrics" in features:
        flat["FEATURE_EMIT_METRICS"] = "true" if _as_bool(features["emit_metrics"]) else "false"
    if "ssm" in features:
        flat["SSM_ENABLED"] = "true" if _as_bool(features["ssm"]) else "false"

    ssm = payload.get("ssm") if isinstance(payload.get("ssm"), dict) else {}
    if ssm.get("parameter"):
        flat["CONFIG_SSM_PARAMETER"] = str(ssm["parameter"])
    return flat


def load_pipeline_file(path: str | Path | None = None) -> tuple[dict[str, str], Path | None]:
    """Read and flatten the pipeline config file. Missing file → empty dict."""

    resolved = Path(path) if path is not None else find_pipeline_config()
    if resolved is None or not resolved.is_file():
        return {}, None
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, resolved
    if not isinstance(payload, dict):
        return {}, resolved
    return parse_pipeline_config(payload), resolved


def fetch_ssm_parameter(
    name: str,
    *,
    endpoint_url: str,
    region: str,
    access_key: str,
    secret_key: str,
) -> dict[str, str]:
    """Fetch an SSM String/SecureString and flatten it if the value is JSON."""

    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        return {}

    kwargs: dict[str, Any] = {
        "region_name": region,
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
        "config": Config(retries={"max_attempts": 2, "mode": "standard"}),
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    try:
        ssm = boto3.client("ssm", **kwargs)
        resp = ssm.get_parameter(Name=name, WithDecryption=True)
    except Exception:
        return {}
    raw = ((resp.get("Parameter") or {}).get("Value")) or ""
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return parse_pipeline_config(payload)


def _pick(layer: dict[str, str], env_name: str) -> str | None:
    if env_name in os.environ:
        return os.environ[env_name]
    if env_name in layer and layer[env_name] != "":
        return layer[env_name]
    return _DEFAULTS.get(env_name)


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
    lookback_days: int = 2
    quality_on_fail: str = "fail"
    quality_max_fail_ratio: float = 0.0
    partition_strategy: str = "hive"
    bronze_prefix: str = "events/"
    silver_prefix: str = "events/"
    gold_prefix: str = "metrics/"
    feature_sfn: bool = True
    feature_emit_metrics: bool = False
    ssm_enabled: bool = False
    config_ssm_parameter: str = "/lakehouse-local/pipeline"

    @property
    def buckets(self) -> tuple[str, str, str]:
        return (self.bronze_bucket, self.silver_bucket, self.gold_bucket)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lookback_days(raw: str | None) -> int:
    from lakehouse.pipeline.late import parse_lookback_days

    return parse_lookback_days(raw, default=2)


def load_settings(
    *,
    load_env_file: bool = True,
    env_file: str | Path | None = None,
    load_config_file: bool = True,
    config_file: str | Path | None = None,
    load_ssm: bool | None = None,
) -> Settings:
    """Build Settings from the environment, config file, and optional SSM.

    When ``load_env_file`` is True, a discovered ``.env`` is applied first
    (without overriding already-set process env vars). Pass ``env_file`` to
    load a specific path instead of searching.
    """
    if env_file is not None:
        load_dotenv(env_file, search=False)
    elif load_env_file:
        load_dotenv()

    file_layer: dict[str, str] = {}
    if load_config_file or config_file is not None:
        file_layer, _ = load_pipeline_file(config_file)

    ssm_name = (
        os.environ.get("CONFIG_SSM_PARAMETER")
        or file_layer.get("CONFIG_SSM_PARAMETER")
        or _DEFAULTS["CONFIG_SSM_PARAMETER"]
    )
    ssm_flag = (
        os.environ.get("SSM_ENABLED")
        or os.environ.get("FEATURE_SSM")
        or file_layer.get("SSM_ENABLED")
        or _DEFAULTS["SSM_ENABLED"]
    )
    should_ssm = _as_bool(ssm_flag) if load_ssm is None else load_ssm

    overlay = dict(file_layer)
    if should_ssm:
        overlay.update(
            fetch_ssm_parameter(
                ssm_name,
                endpoint_url=_pick(overlay, "AWS_ENDPOINT_URL") or _DEFAULTS["AWS_ENDPOINT_URL"],
                region=_pick(overlay, "AWS_DEFAULT_REGION") or _DEFAULTS["AWS_DEFAULT_REGION"],
                access_key=_pick(overlay, "AWS_ACCESS_KEY_ID") or _DEFAULTS["AWS_ACCESS_KEY_ID"],
                secret_key=_pick(overlay, "AWS_SECRET_ACCESS_KEY")
                or _DEFAULTS["AWS_SECRET_ACCESS_KEY"],
            )
        )

    return Settings(
        aws_endpoint_url=_require("AWS_ENDPOINT_URL", _pick(overlay, "AWS_ENDPOINT_URL")),
        aws_region=_require("AWS_DEFAULT_REGION", _pick(overlay, "AWS_DEFAULT_REGION")),
        aws_access_key_id=_require("AWS_ACCESS_KEY_ID", _pick(overlay, "AWS_ACCESS_KEY_ID")),
        aws_secret_access_key=_require(
            "AWS_SECRET_ACCESS_KEY", _pick(overlay, "AWS_SECRET_ACCESS_KEY")
        ),
        bronze_bucket=_require("BRONZE_BUCKET", _pick(overlay, "BRONZE_BUCKET")),
        silver_bucket=_require("SILVER_BUCKET", _pick(overlay, "SILVER_BUCKET")),
        gold_bucket=_require("GOLD_BUCKET", _pick(overlay, "GOLD_BUCKET")),
        pipeline_runs_table=_require("PIPELINE_RUNS_TABLE", _pick(overlay, "PIPELINE_RUNS_TABLE")),
        gold_metrics_table=_require("GOLD_METRICS_TABLE", _pick(overlay, "GOLD_METRICS_TABLE")),
        bronze_events_queue=_require("BRONZE_EVENTS_QUEUE", _pick(overlay, "BRONZE_EVENTS_QUEUE")),
        bronze_events_queue_url=_pick(overlay, "BRONZE_EVENTS_QUEUE_URL") or "",
        bronze_events_dlq=_require("BRONZE_EVENTS_DLQ", _pick(overlay, "BRONZE_EVENTS_DLQ")),
        bronze_events_dlq_url=_pick(overlay, "BRONZE_EVENTS_DLQ_URL") or "",
        lookback_days=_lookback_days(_pick(overlay, "LOOKBACK_DAYS")),
        quality_on_fail=_as_on_fail(_pick(overlay, "QUALITY_ON_FAIL")),
        quality_max_fail_ratio=_as_float(_pick(overlay, "QUALITY_MAX_FAIL_RATIO")),
        partition_strategy=_as_partition(_pick(overlay, "PARTITION_STRATEGY")),
        bronze_prefix=_pick(overlay, "BRONZE_PREFIX") or _DEFAULTS["BRONZE_PREFIX"],
        silver_prefix=_pick(overlay, "SILVER_PREFIX") or _DEFAULTS["SILVER_PREFIX"],
        gold_prefix=_pick(overlay, "GOLD_PREFIX") or _DEFAULTS["GOLD_PREFIX"],
        feature_sfn=_as_bool(_pick(overlay, "FEATURE_SFN"), default=True),
        feature_emit_metrics=_as_bool(_pick(overlay, "FEATURE_EMIT_METRICS")),
        ssm_enabled=should_ssm,
        config_ssm_parameter=ssm_name,
    )


get_settings = load_settings
