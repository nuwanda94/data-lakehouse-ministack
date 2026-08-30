"""Named deployment environments (local MiniStack vs real AWS).

``LAKEHOUSE_ENV`` selects a profile. Terraform var-files live in
``infra/terraform/envs/<name>.tfvars``. Resource names stay env-prefixed so
the same module can be applied twice without colliding.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

KNOWN_ENVIRONMENTS = ("local", "aws")
_ALIASES = {
    "local": "local",
    "ministack": "local",
    "dev": "local",
    "aws": "aws",
    "prod": "aws",
    "production": "aws",
}


@dataclass(frozen=True)
class EnvironmentProfile:
    """Resolved multi-environment profile."""

    name: str
    display_name: str
    aws_endpoint_url: str
    aws_region: str
    project: str
    requires_ministack: bool
    use_static_credentials: bool
    force_destroy: bool
    enable_glue: bool
    enable_athena: bool
    ssm_enabled: bool
    tfvars_relpath: str
    bronze_bucket: str
    silver_bucket: str
    gold_bucket: str
    pipeline_runs_table: str
    gold_metrics_table: str
    bronze_events_queue: str
    bronze_events_dlq: str
    glue_database: str
    athena_workgroup: str
    config_ssm_parameter: str
    notes: str

    @property
    def terraform_workspace(self) -> str:
        return self.name

    def tfvars_path(self, root: Path | None = None) -> Path:
        base = root if root is not None else Path.cwd()
        return (base / self.tfvars_relpath).resolve()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["terraform_workspace"] = self.terraform_workspace
        return payload


_PROFILES: dict[str, EnvironmentProfile] = {
    "local": EnvironmentProfile(
        name="local",
        display_name="MiniStack (local)",
        aws_endpoint_url="http://localhost:4566",
        aws_region="us-east-1",
        project="lakehouse-local",
        requires_ministack=True,
        use_static_credentials=True,
        force_destroy=True,
        enable_glue=False,
        enable_athena=False,
        ssm_enabled=False,
        tfvars_relpath="infra/terraform/envs/local.tfvars",
        bronze_bucket="lakehouse-local-bronze",
        silver_bucket="lakehouse-local-silver",
        gold_bucket="lakehouse-local-gold",
        pipeline_runs_table="lakehouse-local-pipeline-runs",
        gold_metrics_table="lakehouse-local-gold-metrics",
        bronze_events_queue="lakehouse-local-bronze-events",
        bronze_events_dlq="lakehouse-local-bronze-events-dlq",
        glue_database="lakehouse_local",
        athena_workgroup="lakehouse-local",
        config_ssm_parameter="/lakehouse-local/pipeline",
        notes="Default. Dummy credentials, path-style S3, MiniStack on :4566.",
    ),
    "aws": EnvironmentProfile(
        name="aws",
        display_name="Real AWS",
        aws_endpoint_url="",
        aws_region="us-east-1",
        project="lakehouse-aws",
        requires_ministack=False,
        use_static_credentials=False,
        force_destroy=False,
        enable_glue=True,
        enable_athena=True,
        ssm_enabled=True,
        tfvars_relpath="infra/terraform/envs/aws.tfvars",
        bronze_bucket="lakehouse-aws-bronze",
        silver_bucket="lakehouse-aws-silver",
        gold_bucket="lakehouse-aws-gold",
        pipeline_runs_table="lakehouse-aws-pipeline-runs",
        gold_metrics_table="lakehouse-aws-gold-metrics",
        bronze_events_queue="lakehouse-aws-bronze-events",
        bronze_events_dlq="lakehouse-aws-bronze-events-dlq",
        glue_database="lakehouse_aws",
        athena_workgroup="lakehouse-aws",
        config_ssm_parameter="/lakehouse-aws/pipeline",
        notes=(
            "Uses the default AWS credential chain. Override globally unique "
            "S3 bucket names in infra/terraform/envs/aws.tfvars before apply."
        ),
    ),
}


def normalize_environment(name: str | None) -> str:
    raw = (name or os.environ.get("LAKEHOUSE_ENV") or "local").strip().lower()
    if raw not in _ALIASES:
        known = ", ".join(KNOWN_ENVIRONMENTS)
        raise ValueError(f"Unknown environment {name!r}. Expected one of: {known}")
    return _ALIASES[raw]


def get_environment(name: str | None = None) -> EnvironmentProfile:
    return _PROFILES[normalize_environment(name)]


def list_environments() -> list[EnvironmentProfile]:
    return [_PROFILES[key] for key in KNOWN_ENVIRONMENTS]


def describe_environment(name: str | None = None) -> dict[str, Any]:
    current = get_environment(name)
    return {
        "current": current.to_dict(),
        "available": [profile.name for profile in list_environments()],
        "aliases": dict(_ALIASES),
        "selected_via": "LAKEHOUSE_ENV" if os.environ.get("LAKEHOUSE_ENV") else "default",
    }
