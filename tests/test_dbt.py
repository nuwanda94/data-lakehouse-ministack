from __future__ import annotations

from lakehouse.catalog import GLUE_DATABASE, GOLD_TABLE, SILVER_TABLE
from lakehouse.cli import main
from lakehouse.dbt import lint_project, load_project, project_dir


def test_project_layout_exists() -> None:
    root = project_dir()
    assert (root / "dbt_project.yml").is_file()
    assert (root / "models" / "sources.yml").is_file()
    assert (root / "models" / "schema.yml").is_file()
    assert (root / "models" / "staging" / "stg_daily_event_metrics.sql").is_file()
    assert (root / "models" / "marts" / "fct_daily_event_metrics.sql").is_file()
    assert (root / "models" / "marts" / "fct_daily_purchase_revenue.sql").is_file()
    assert (root / "models" / "marts" / "dim_event_type.sql").is_file()


def test_load_and_lint_project() -> None:
    project = load_project()
    assert project.name == "lakehouse"
    assert project.profile == "lakehouse"
    names = {model.name for model in project.models}
    assert names == {
        "stg_daily_event_metrics",
        "fct_daily_event_metrics",
        "fct_daily_purchase_revenue",
        "dim_event_type",
    }
    issues = lint_project(project)
    assert issues == []


def test_compiled_sql_uses_glue_names() -> None:
    project = load_project()
    by_name = {model.name: model for model in project.models}
    staging = by_name["stg_daily_event_metrics"]
    assert f"{GLUE_DATABASE}.{GOLD_TABLE}" in staging.compiled_sql
    assert "metric as event_type" in staging.compiled_sql
    purchase = by_name["fct_daily_purchase_revenue"]
    assert "stg_daily_event_metrics" in purchase.compiled_sql
    assert "purchase" in purchase.compiled_sql
    assert "{{" not in staging.compiled_sql


def test_sources_include_silver_and_gold() -> None:
    project = load_project()
    tables = {table["name"] for source in project.sources for table in source.get("tables") or []}
    assert GOLD_TABLE in tables
    assert SILVER_TABLE in tables
    assert project.sources[0]["schema"] == GLUE_DATABASE


def test_cli_dbt_ok(capsys: object) -> None:
    assert main(["dbt"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"ok": true' in captured.out
    assert "fct_daily_event_metrics" in captured.out
