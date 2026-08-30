from __future__ import annotations

import pytest

from lakehouse.cli import main
from lakehouse.environments import (
    get_environment,
    list_environments,
    normalize_environment,
)


def test_normalize_aliases() -> None:
    assert normalize_environment("local") == "local"
    assert normalize_environment("ministack") == "local"
    assert normalize_environment("AWS") == "aws"
    assert normalize_environment("prod") == "aws"


def test_normalize_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown environment"):
        normalize_environment("staging")


def test_local_profile_points_at_ministack() -> None:
    profile = get_environment("local")
    assert profile.requires_ministack is True
    assert profile.aws_endpoint_url.endswith(":4566")
    assert profile.force_destroy is True
    assert profile.enable_glue is False
    assert profile.tfvars_relpath.endswith("local.tfvars")
    assert profile.terraform_workspace == "local"


def test_aws_profile_targets_real_account() -> None:
    profile = get_environment("aws")
    assert profile.requires_ministack is False
    assert profile.aws_endpoint_url == ""
    assert profile.use_static_credentials is False
    assert profile.force_destroy is False
    assert profile.enable_glue is True
    assert profile.enable_athena is True
    assert profile.bronze_bucket.startswith("lakehouse-aws-")


def test_list_environments_order() -> None:
    names = [item.name for item in list_environments()]
    assert names == ["local", "aws"]


def test_cli_env_json(capsys: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAKEHOUSE_ENV", raising=False)
    assert main(["env"]) == 0
    captured = capsys.readouterr()
    assert '"name": "local"' in captured.out
    assert "available" in captured.out
