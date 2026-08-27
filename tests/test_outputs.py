from __future__ import annotations

import json
from pathlib import Path

from lakehouse.ops.outputs import (
    OUTPUT_ENV_MAP,
    collect_outputs,
    default_outputs,
    format_exports,
    parse_output_json,
    parse_tfstate,
    write_env_file,
)


def test_parse_output_json_maps_known_keys() -> None:
    payload = {
        "bronze_bucket": {"sensitive": False, "type": "string", "value": "tf-bronze"},
        "gold_metrics_table": {"value": "tf-metrics"},
        "ignored": {"value": "nope"},
    }
    parsed = parse_output_json(payload)
    assert parsed["BRONZE_BUCKET"] == "tf-bronze"
    assert parsed["GOLD_METRICS_TABLE"] == "tf-metrics"
    assert "ignored" not in parsed
    assert "SILVER_BUCKET" not in parsed


def test_parse_tfstate_reads_outputs_block() -> None:
    state = {
        "version": 4,
        "outputs": {
            "silver_bucket": {"value": "state-silver"},
            "aws_region": {"value": "eu-west-1"},
        },
    }
    parsed = parse_tfstate(state)
    assert parsed == {
        "SILVER_BUCKET": "state-silver",
        "AWS_DEFAULT_REGION": "eu-west-1",
    }


def test_collect_outputs_reads_tfstate_without_terraform(tmp_path: Path) -> None:
    tf_dir = tmp_path / "infra" / "terraform"
    tf_dir.mkdir(parents=True)
    state = {
        "version": 4,
        "outputs": {
            "bronze_bucket": {"value": "from-state-bronze"},
            "pipeline_runs_table": {"value": "from-state-runs"},
        },
    }
    (tf_dir / "terraform.tfstate").write_text(json.dumps(state), encoding="utf-8")

    values = collect_outputs(tf_dir)
    assert values["BRONZE_BUCKET"] == "from-state-bronze"
    assert values["PIPELINE_RUNS_TABLE"] == "from-state-runs"
    # unspecified keys fall back to documented defaults
    assert values["GOLD_BUCKET"] == default_outputs()["GOLD_BUCKET"]


def test_collect_outputs_falls_back_to_defaults(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    values = collect_outputs(empty)
    assert values == default_outputs()
    assert set(values) == set(OUTPUT_ENV_MAP.values())


def test_format_exports_and_write_env(tmp_path: Path) -> None:
    values = {
        "AWS_ENDPOINT_URL": "http://localhost:4566",
        "AWS_DEFAULT_REGION": "us-east-1",
        "BRONZE_BUCKET": "b",
        "SILVER_BUCKET": "s",
        "GOLD_BUCKET": "g",
        "PIPELINE_RUNS_TABLE": "r",
        "GOLD_METRICS_TABLE": "m",
    }
    plain = format_exports(values)
    assert "BRONZE_BUCKET=b" in plain
    assert "export " not in plain
    exported = format_exports(values, export=True)
    assert exported.startswith("export AWS_ENDPOINT_URL=")

    dest = write_env_file(tmp_path / "generated.env", values)
    text = dest.read_text(encoding="utf-8")
    assert "GOLD_METRICS_TABLE=m" in text
