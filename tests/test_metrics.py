from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from lakehouse.cli import main
from lakehouse.config import Settings
from lakehouse.metrics import (
    NAMESPACE,
    emit_points,
    emit_run_metrics,
    estimated_bytes,
    metric_catalog,
    points_from_run,
    record,
    recorded_metrics,
    reset_metrics,
)


def _settings(*, emit: bool) -> Settings:
    return Settings(
        aws_endpoint_url="http://localhost:4566",
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        bronze_bucket="b",
        silver_bucket="s",
        gold_bucket="g",
        pipeline_runs_table="runs",
        gold_metrics_table="gold",
        bronze_events_queue="q",
        bronze_events_queue_url="",
        feature_emit_metrics=emit,
    )


def setup_function() -> None:
    reset_metrics()


def test_catalog_covers_plan_metrics() -> None:
    names = {item["name"] for item in metric_catalog()}
    assert "RecordsProcessed" in names
    assert "QualityFailures" in names
    assert "PipelineLagSeconds" in names
    assert "EstimatedBytes" in names


def test_points_from_silver_run() -> None:
    started = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    finished = started + timedelta(milliseconds=40)
    points = points_from_run(
        zone="silver",
        metrics={"valid": 10, "quarantined": 2, "late": 1, "silver_written": 10},
        status="succeeded",
        started_at=started,
        finished_at=finished,
    )
    by_name = {p.name: p for p in points}
    assert by_name["RecordsProcessed"].value == 10
    assert by_name["QualityFailures"].value == 2
    assert by_name["LateEvents"].value == 1
    assert by_name["ObjectsWritten"].value == 10
    assert by_name["EstimatedBytes"].value == estimated_bytes(records=10)
    assert by_name["RunDurationMilliseconds"].value == 40
    assert recorded_metrics()


def test_quality_fail_ratio() -> None:
    points = points_from_run(
        zone="quality",
        metrics={"rows_scanned": 8, "rows_failed": 2, "fail_ratio": 0.25},
        status="quality_failed",
    )
    by_name = {p.name: p for p in points}
    assert by_name["QualityFailRatio"].value == 0.25
    assert by_name["QualityFailures"].value == 2


def test_lag_from_event_ts() -> None:
    event_ts = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)
    points = points_from_run(
        zone="gold",
        metrics={"silver_read": 3, "gold_written": 2},
        finished_at=finished,
        latest_event_ts=event_ts,
    )
    by_name = {p.name: p for p in points}
    assert by_name["PipelineLagSeconds"].value == 86400
    assert by_name["EstimatedBytes"].value == estimated_bytes(records=3, gold_objects=2)


def test_emit_disabled_stays_in_buffer() -> None:
    point = record("RecordsProcessed", 1, zone="bronze")
    result = emit_points([point], settings=_settings(emit=False))
    assert result["namespace"] == NAMESPACE
    assert result["enabled"] is False
    assert result["emitted"] == 0
    assert result["backend"] == "buffer"


class _FakeCW:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def test_emit_enabled_uses_cloudwatch() -> None:
    cw = _FakeCW()
    result = emit_run_metrics(
        zone="bronze",
        metrics={"object_count": 4},
        status="succeeded",
        settings=_settings(emit=True),
        cloudwatch=cw,
    )
    assert result["backend"] == "cloudwatch"
    assert result["emitted"] >= 1
    assert cw.calls[0]["Namespace"] == NAMESPACE
    names = {item["MetricName"] for item in cw.calls[0]["MetricData"]}
    assert "RecordsProcessed" in names


def test_emit_never_raises_on_cloudwatch_error() -> None:
    class Boom:
        def put_metric_data(self, **kwargs: Any) -> None:
            raise RuntimeError("no cloudwatch")

    result = emit_run_metrics(
        zone="gold",
        metrics={"silver_read": 1, "gold_written": 1},
        settings=_settings(emit=True),
        cloudwatch=Boom(),
    )
    assert result["backend"] == "buffer"
    assert result["error"]
    assert result["emitted"] == 0


def test_cli_metrics(capsys: object) -> None:
    assert main(["metrics"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Lakehouse/Medallion" in captured.out
    assert "RecordsProcessed" in captured.out
