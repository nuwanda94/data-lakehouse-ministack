from __future__ import annotations

from pathlib import Path

from lakehouse.catalog import (
    GLUE_DATABASE,
    catalog_tables,
    gold_table,
    register_catalog,
    silver_table,
)
from lakehouse.cli import main
from lakehouse.contracts import load_contract


def test_silver_table_matches_contract() -> None:
    spec = load_contract("silver")
    table = silver_table()
    assert table.database == GLUE_DATABASE
    assert table.name == spec["name"]
    assert table.zone == "silver"
    assert table.location.endswith("/events/")
    names = [col.name for col in table.columns]
    parts = [col.name for col in table.partition_keys]
    assert parts == spec["partitioning"]["hive"]
    assert "event_id" in names
    assert "event_ts" in names
    assert "_late" in names
    assert "event_type" not in names  # partition only
    assert "dt" not in names
    types = {col.name: col.type for col in table.columns}
    assert types["quantity"] == "bigint"
    assert types["amount_usd"] == "double"
    assert types["event_ts"] == "timestamp"
    assert types["_late"] == "boolean"


def test_gold_table_uses_metric_partition() -> None:
    spec = load_contract("gold")
    table = gold_table()
    assert table.name == spec["name"]
    assert [col.name for col in table.partition_keys] == ["metric", "dt"]
    names = [col.name for col in table.columns]
    assert names == ["events", "amount_usd"]
    types = {col.name: col.type for col in table.columns}
    assert types["events"] == "bigint"
    assert types["amount_usd"] == "double"
    assert table.location.endswith("/metrics/")


def test_catalog_tables_order() -> None:
    tables = catalog_tables()
    assert [t.zone for t in tables] == ["silver", "gold"]


def test_register_catalog_always_returns_specs() -> None:
    result = register_catalog()
    assert result["database"] == GLUE_DATABASE
    names = {item["name"] for item in result["tables"]}
    assert names == {"commerce_event_conformed", "daily_event_metrics"}
    assert result["backend"] in {"glue", "spec"}
    assert "commerce_event_conformed" in result["actions"]


def test_terraform_glue_matches_python_names() -> None:
    tf_dir = Path(__file__).resolve().parents[1] / "infra" / "terraform"
    glue = (tf_dir / "glue.tf").read_text(encoding="utf-8")
    variables = (tf_dir / "variables.tf").read_text(encoding="utf-8")
    assert "commerce_event_conformed" in variables
    assert "daily_event_metrics" in variables
    assert "enable_glue" in variables
    assert "event_type" in glue
    assert 'name    = "metric"' in glue
    assert "org.openx.data.jsonserde.JsonSerDe" in glue


def test_cli_catalog(capsys: object) -> None:
    assert main(["catalog"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "commerce_event_conformed" in captured.out
    assert "daily_event_metrics" in captured.out
