from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lakehouse.catalog import gold_table, silver_table
from lakehouse.cli import main
from lakehouse.partitions import (
    DEFAULT_DT_START,
    EVENT_TYPES,
    describe_partitions,
    discover_s3_partitions,
    gold_projection,
    parse_hive_key,
    projected_partitions,
    silver_projection,
)


def test_parse_hive_key() -> None:
    parsed = parse_hive_key("events/event_type=purchase/dt=2026-01-02/evt-1.json")
    assert parsed == {"event_type": "purchase", "dt": "2026-01-02"}
    assert parse_hive_key("metrics/part-000.json") == {}


def test_discover_s3_partitions_dedupes() -> None:
    keys = [
        "events/event_type=purchase/dt=2026-01-02/a.json",
        "events/event_type=purchase/dt=2026-01-02/b.json",
        "events/event_type=refund/dt=2026-01-02/c.json",
    ]
    found = discover_s3_partitions(keys)
    assert {"event_type": "purchase", "dt": "2026-01-02"} in found
    assert {"event_type": "refund", "dt": "2026-01-02"} in found
    assert len(found) == 2


def test_projected_partitions_grid() -> None:
    rows = projected_partitions(
        enum_key="event_type",
        enum_values=("purchase", "refund"),
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
    )
    assert len(rows) == 4
    assert {"event_type": "purchase", "dt": "2026-01-01"} in rows
    assert {"event_type": "refund", "dt": "2026-01-02"} in rows


def test_projected_partitions_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        projected_partitions(
            enum_key="metric",
            enum_values=EVENT_TYPES,
            start=date(2026, 1, 2),
            end=date(2026, 1, 1),
        )


def test_silver_projection_parameters() -> None:
    params = silver_projection()
    assert params["projection.enabled"] == "true"
    assert params["projection.event_type.type"] == "enum"
    assert params["projection.event_type.values"] == "page_view,add_to_cart,purchase,refund"
    assert params["projection.dt.type"] == "date"
    assert params["projection.dt.format"] == "yyyy-MM-dd"
    assert params["projection.dt.range"].startswith(f"{DEFAULT_DT_START},")
    template = params["storage.location.template"]
    assert template.startswith("s3://")
    assert template.endswith("/events/event_type=${event_type}/dt=${dt}")


def test_gold_projection_uses_metric_key() -> None:
    params = gold_projection()
    assert params["projection.metric.type"] == "enum"
    assert "projection.event_type.values" not in params
    template = params["storage.location.template"]
    assert template.endswith("/metrics/metric=${metric}/dt=${dt}")
    assert "${metric}" in template


def test_catalog_tables_embed_projection() -> None:
    silver = silver_table()
    gold = gold_table()
    assert silver.projection["projection.enabled"] == "true"
    assert gold.projection["projection.metric.values"].startswith("page_view")


def test_terraform_glue_has_projection() -> None:
    glue = (Path(__file__).resolve().parents[1] / "infra" / "terraform" / "glue.tf").read_text(
        encoding="utf-8"
    )
    assert "projection.enabled" in glue
    assert "projection.event_type.values" in glue
    assert "projection.metric.values" in glue
    assert "storage.location.template" in glue
    # Terraform must escape Athena ${partition} placeholders.
    assert "$${event_type}" in glue
    assert "$${metric}" in glue


def test_describe_partitions_shape() -> None:
    result = describe_partitions()
    assert result["strategy"] == "hive+projection"
    assert result["event_types"] == list(EVENT_TYPES)
    assert "projection.enabled" in result["silver"]["projection"]
    assert "projection.enabled" in result["gold"]["projection"]
    assert isinstance(result["silver"]["window"], list)


def test_cli_partitions(capsys: object) -> None:
    assert main(["partitions"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "projection.enabled" in captured.out
    assert "hive+projection" in captured.out
