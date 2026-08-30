from __future__ import annotations

from pathlib import Path

import pytest

from lakehouse.athena import (
    WORKGROUP,
    get_named_query,
    named_queries,
    register_athena,
    result_location,
    run_named_query,
    workgroup_config,
)
from lakehouse.catalog import GLUE_DATABASE, GOLD_TABLE, SILVER_TABLE
from lakehouse.cli import main


def test_named_query_set() -> None:
    names = [q.name for q in named_queries()]
    assert names == [
        "gold_daily_totals",
        "gold_purchase_revenue",
        "gold_last_7_days",
        "silver_late_event_counts",
    ]
    gold_sql = get_named_query("gold_daily_totals").sql
    assert f"{GLUE_DATABASE}.{GOLD_TABLE}" in gold_sql
    silver_sql = get_named_query("silver_late_event_counts").sql
    assert f"{GLUE_DATABASE}.{SILVER_TABLE}" in silver_sql
    assert "_late" in silver_sql


def test_unknown_named_query() -> None:
    with pytest.raises(KeyError, match="unknown named query"):
        get_named_query("not_a_query")


def test_workgroup_points_at_gold_results() -> None:
    cfg = workgroup_config()
    assert cfg["name"] == WORKGROUP
    assert cfg["bytes_scanned_cutoff_per_query"] == 100 * 1024 * 1024
    assert cfg["enforce_workgroup_configuration"] is True
    assert result_location().endswith("/athena-results/")
    assert cfg["result_location"].endswith("/athena-results/")


def test_register_athena_always_returns_spec() -> None:
    result = register_athena()
    assert result["backend"] in {"athena", "spec"}
    names = {item["name"] for item in result["workgroup"]["named_queries"]}
    assert "gold_daily_totals" in names
    assert "workgroup" in result["actions"]


def test_run_named_query_falls_back_to_sql() -> None:
    result = run_named_query("gold_purchase_revenue")
    assert result["name"] == "gold_purchase_revenue"
    assert "WHERE metric = 'purchase'" in result["sql"]
    assert result["backend"] in {"athena", "spec"}


def test_terraform_athena_matches_python_names() -> None:
    tf_dir = Path(__file__).resolve().parents[1] / "infra" / "terraform"
    athena = (tf_dir / "athena.tf").read_text(encoding="utf-8")
    variables = (tf_dir / "variables.tf").read_text(encoding="utf-8")
    assert "enable_athena" in variables
    assert 'default = "lakehouse-local"' in variables
    for name in (
        "gold_daily_totals",
        "gold_purchase_revenue",
        "gold_last_7_days",
        "silver_late_event_counts",
    ):
        assert name in athena
    assert "bytes_scanned_cutoff_per_query     = 104857600" in athena
    assert "athena-results/" in athena


def test_cli_athena(capsys: object) -> None:
    assert main(["athena"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "gold_daily_totals" in captured.out
    assert "lakehouse-local" in captured.out


def test_cli_athena_named(capsys: object) -> None:
    assert main(["athena", "--name", "gold_last_7_days"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "gold_last_7_days" in captured.out
    assert "date_add" in captured.out
