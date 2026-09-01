"""CLI entrypoint for local lakehouse operations."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lakehouse")
    parser.add_argument("--version", action="store_true", help="Print package version")
    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser(
        "health",
        help="Probe Mini MiniStack S3 + DynamoDB and print a JSON report",
    )

    p_seed = sub.add_parser("seed", help="Write synthetic commerce events to Bronze")
    p_seed.add_argument("--count", type=int, default=20)

    sub.add_parser("pipeline", help="Run Bronze → Silver → quality → Gold locally")
    sub.add_parser("ingest", help="Drain Bronze SQS / process pending Bronze objects")
    sub.add_parser("silver", help="Cleanse Bronze → Silver")
    sub.add_parser("quality", help="Run Silver quality gate")
    sub.add_parser("gold", help="Aggregate Silver → Gold metrics")
    sub.add_parser("query", help="Print Gold summary")
    sub.add_parser(
        "catalog",
        help="Describe (and best-effort register) Glue Silver/Gold tables",
    )
    sub.add_parser(
        "partitions",
        help="Describe Athena partition projection + discover Hive keys on S3",
    )
    sub.add_parser(
        "metrics",
        help="Describe the CloudWatch metric catalog and in-process buffer",
    )
    p_athena = sub.add_parser(
        "athena",
        help="Describe Athena workgroup + named queries (optional --name to start one)",
    )
    p_athena.add_argument(
        "--name",
        default=None,
        help="Named query to start (gold_daily_totals, gold_purchase_revenue, ...)",
    )
    sub.add_parser("runs", help="List pipeline runs from DynamoDB")
    sub.add_parser(
        "sfn",
        help="Walk the Step Functions graph locally (ingest → silver → quality → gold)",
    )
    sub.add_parser("sfn-def", help="Print the medallion Amazon States Language definition")

    p_dlq = sub.add_parser("dlq", help="Peek the Bronze events dead-letter queue")
    p_dlq.add_argument("--max", type=int, default=10, dest="max_messages")

    p_redrive = sub.add_parser(
        "redrive",
        help="Move Bronze DLQ messages back onto the source events queue",
    )
    p_redrive.add_argument("--max", type=int, default=10, dest="max_messages")

    p_reprocess = sub.add_parser(
        "reprocess",
        help="Rebuild Gold partitions for a late-arriving lookback window",
    )
    p_reprocess.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Override LOOKBACK_DAYS (inclusive calendar days behind as-of)",
    )
    p_reprocess.add_argument(
        "--as-of",
        default=None,
        help="Window end date or ISO timestamp (default: now UTC)",
    )

    sub.add_parser(
        "dbt",
        help="Parse and lint the transform/dbt Gold project (no dbt-core required)",
    )
    p_ui = sub.add_parser(
        "ui",
        help="Render the Gold query dashboard (HTML + named Athena SQL)",
    )
    p_ui.add_argument(
        "--out",
        default=None,
        help="Write a self-contained HTML dashboard to this path",
    )
    p_ui.add_argument(
        "--serve",
        action="store_true",
        help="Serve the HTML from a stdlib HTTP server (blocking)",
    )
    p_ui.add_argument("--host", default="127.0.0.1")
    p_ui.add_argument("--port", type=int, default=8765)

    p_qdash = sub.add_parser(
        "quality-dashboard",
        help="Render the Silver quality-gate dashboard (HTML + named checks)",
    )
    p_qdash.add_argument(
        "--out",
        default=None,
        help="Write a self-contained HTML dashboard to this path",
    )

    p_lineage = sub.add_parser(
        "lineage",
        help="Describe Bronze → Silver → quality → Gold dataset lineage",
    )
    p_lineage.add_argument(
        "--out",
        default=None,
        help="Write a Mermaid flowchart to this path",
    )

    p_sla = sub.add_parser(
        "sla",
        help="Evaluate Gold freshness SLA (last-written vs max-age hours)",
    )
    p_sla.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Override LAKEHOUSE_GOLD_SLA_HOURS (default 24)",
    )

    p_ret = sub.add_parser(
        "retention",
        help="Plan Gold partition expiry (Hive dt vs retention days)",
    )
    p_ret.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override LAKEHOUSE_GOLD_RETENTION_DAYS (default 90)",
    )
    p_ret.add_argument(
        "--apply",
        action="store_true",
        help="Delete expired Gold objects (default is dry-run)",
    )

    p_qret = sub.add_parser(
        "quarantine-retention",
        help="Plan Silver quarantine TTL expiry (LastModified vs retention days)",
    )
    p_qret.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override LAKEHOUSE_QUARANTINE_RETENTION_DAYS (default 14)",
    )
    p_qret.add_argument(
        "--apply",
        action="store_true",
        help="Delete expired quarantine objects (default is dry-run)",
    )

    p_sret = sub.add_parser(
        "silver-retention",
        help="Plan Silver cleaned-event expiry (Hive dt vs retention days)",
    )
    p_sret.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override LAKEHOUSE_SILVER_RETENTION_DAYS (default 60)",
    )
    p_sret.add_argument(
        "--apply",
        action="store_true",
        help="Delete expired Silver cleaned events (default is dry-run)",
    )

    p_compact = sub.add_parser(
        "compact",
        help="Plan Gold metric-object compact / rewrite (objects vs max)",
    )
    p_compact.add_argument(
        "--max-objects",
        type=int,
        default=None,
        help="Override LAKEHOUSE_GOLD_COMPACT_MAX_OBJECTS (default 2)",
    )
    p_compact.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite fragmented Gold partitions (default is dry-run)",
    )

    p_maintain = sub.add_parser(
        "maintain",
        help="Gold expire-then-compact (retention then compact)",
    )
    p_maintain.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override LAKEHOUSE_GOLD_RETENTION_DAYS (default 90)",
    )
    p_maintain.add_argument(
        "--max-objects",
        type=int,
        default=None,
        help="Override LAKEHOUSE_GOLD_COMPACT_MAX_OBJECTS (default 2)",
    )
    p_maintain.add_argument(
        "--apply",
        action="store_true",
        help="Expire then compact Gold partitions (default is dry-run)",
    )

    p_bret = sub.add_parser(
        "bronze-retention",
        help="Plan Bronze raw event expiry (Hive dt vs retention days)",
    )
    p_bret.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override LAKEHOUSE_BRONZE_RETENTION_DAYS (default 30)",
    )
    p_bret.add_argument(
        "--apply",
        action="store_true",
        help="Delete expired Bronze objects (default is dry-run)",
    )

    p_bcompact = sub.add_parser(
        "bronze-compact",
        help="Plan Bronze raw-object compact / rewrite (objects vs max)",
    )
    p_bcompact.add_argument(
        "--max-objects",
        type=int,
        default=None,
        help="Override LAKEHOUSE_BRONZE_COMPACT_MAX_OBJECTS (default 8)",
    )
    p_bcompact.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite fragmented Bronze partitions (default is dry-run)",
    )
