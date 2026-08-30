"""Fetch Terraform outputs and map them onto lakehouse environment variables.

Used by ``scripts/get_outputs.sh`` and ``python -m lakehouse outputs``.
Does not require the Terraform CLI when ``terraform.tfstate`` is present.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from lakehouse.config import _DEFAULTS

OUTPUT_ENV_MAP: dict[str, str] = {
    "aws_endpoint_url": "AWS_ENDPOINT_URL",
    "aws_region": "AWS_DEFAULT_REGION",
    "bronze_bucket": "BRONZE_BUCKET",
    "silver_bucket": "SILVER_BUCKET",
    "gold_bucket": "GOLD_BUCKET",
    "pipeline_runs_table": "PIPELINE_RUNS_TABLE",
    "gold_metrics_table": "GOLD_METRICS_TABLE",
    "bronze_events_queue": "BRONZE_EVENTS_QUEUE",
    "bronze_events_queue_url": "BRONZE_EVENTS_QUEUE_URL",
    "bronze_events_dlq": "BRONZE_EVENTS_DLQ",
    "bronze_events_dlq_url": "BRONZE_EVENTS_DLQ_URL",
    "pipeline_ssm_parameter": "CONFIG_SSM_PARAMETER",
}

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TF_DIR = REPO_ROOT / "infra" / "terraform"


def default_outputs() -> dict[str, str]:
    """Documented defaults used when Terraform has not been applied."""

    return {env_name: _DEFAULTS[env_name] for env_name in OUTPUT_ENV_MAP.values()}


def _value_from_output_item(item: Any) -> str | None:
    if item is None:
        return None
    if isinstance(item, dict) and "value" in item:
        value = item["value"]
    else:
        value = item
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_output_json(payload: dict[str, Any]) -> dict[str, str]:
    """Parse ``terraform output -json`` (or an equivalent mapping)."""

    resolved: dict[str, str] = {}
    for tf_name, env_name in OUTPUT_ENV_MAP.items():
        value = _value_from_output_item(payload.get(tf_name))
        if value is not None:
            resolved[env_name] = value
    return resolved


def parse_tfstate(payload: dict[str, Any]) -> dict[str, str]:
    """Parse the ``outputs`` block of a local Terraform state file."""

    outputs = payload.get("outputs")
    if not isinstance(outputs, dict):
        return {}
    return parse_output_json(outputs)


def _run_terraform_output(tf_dir: Path) -> dict[str, str] | None:
    terraform = shutil.which("terraform")
    if terraform is None:
        return None
    try:
        completed = subprocess.run(
            [terraform, "output", "-json"],
            cwd=tf_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    parsed = parse_output_json(payload)
    return parsed or None


def _read_tfstate(tf_dir: Path) -> dict[str, str] | None:
    state_path = tf_dir / "terraform.tfstate"
    if not state_path.is_file():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    parsed = parse_tfstate(payload)
    return parsed or None


def collect_outputs(
    tf_dir: str | Path | None = None,
    *,
    allow_defaults: bool = True,
) -> dict[str, str]:
    """Return env-var mapping from Terraform, state file, or defaults."""

    directory = Path(tf_dir) if tf_dir is not None else DEFAULT_TF_DIR
    resolved = _run_terraform_output(directory)
    if resolved:
        merged = default_outputs()
        merged.update(resolved)
        return merged

    resolved = _read_tfstate(directory)
    if resolved:
        merged = default_outputs()
        merged.update(resolved)
        return merged

    if allow_defaults:
        return default_outputs()
    raise FileNotFoundError(
        f"No Terraform outputs found under {directory} "
        "(need `terraform output -json` or terraform.tfstate)"
    )


def format_exports(values: dict[str, str], *, export: bool = False) -> str:
    """Render KEY=value lines, optionally prefixed with ``export``."""

    prefix = "export " if export else ""
    lines = [f"{prefix}{key}={values[key]}" for key in OUTPUT_ENV_MAP.values() if key in values]
    return "\n".join(lines) + ("\n" if lines else "")


def write_env_file(path: str | Path, values: dict[str, str]) -> Path:
    """Write a dotenv file with the resolved Terraform-backed settings."""

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(format_exports(values, export=False), encoding="utf-8")
    return dest
