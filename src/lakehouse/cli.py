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

    p_stream = sub.add_parser(
        "stream",
        help="Optional Kinesis / Firehose producer into Bronze",
    )
    p_stream.add_argument("--count", type=int, default=20)
    p_stream.add_argument(
        "--mode",
        choices=("auto", "live", "offline"),
        default="auto",
        help="auto tries MiniStack then falls back to an in-memory path",
    )
    p_stream.add_argument(
        "--sink",
        choices=("kinesis", "firehose", "both"),
        default="both",
    )

    p_demo = sub.add_parser(
        "demo",
        help="Seed → pipeline → query and assert Gold is populated",
    )
    p_demo.add_argument("--count", type=int, default=20)
    p_demo.add_argument(
        "--mode",
        choices=("auto", "live", "offline"),
        default="auto",
        help="auto tries MiniStack then falls back to an in-memory path",
    )

    sub.add_parser(
        "env",
        help="Print the resolved local|aws environment profile as JSON",
    )

    p_settings = sub.add_parser("settings", help="Print resolved settings as JSON")
    p_settings.add_argument("--no-dotenv", action="store_true")

    sub.add_parser("contracts", help="Validate zone contracts against in-repo producers")
    sub.add_parser(
        "security",
        help="Scan the repo for secrets and verify Checkov/Trivy config files",
    )

    p_outputs = sub.add_parser("outputs", help="Emit Terraform outputs as env exports")
    p_outputs.add_argument("--tf-dir", default="infra/terraform")
    p_outputs.add_argument("--export", action="store_true")
    p_outputs.add_argument("--json", "--as-json", dest="as_json", action="store_true")
    p_outputs.add_argument("--write-env", default=None)

    args = parser.parse_args(argv)

    if args.version:
        from lakehouse import __version__

        print(__version__)
        return 0

    if args.command is None:
        parser.error("the following arguments are required: command")

    if args.command == "env":
        from lakehouse.environments import describe_environment

        print(json.dumps(describe_environment(), indent=2))
        return 0

    if args.command == "settings":
        from lakehouse.config import load_settings

        settings = load_settings(load_env_file=not args.no_dotenv)
        payload = {
            "aws_endpoint_url": settings.aws_endpoint_url,
            "aws_region": settings.aws_region,
            "bronze_bucket": settings.bronze_bucket,
            "silver_bucket": settings.silver_bucket,
            "gold_bucket": settings.gold_bucket,
            "pipeline_runs_table": settings.pipeline_runs_table,
            "gold_metrics_table": settings.gold_metrics_table,
            "bronze_events_queue": settings.bronze_events_queue,
            "bronze_events_queue_url": settings.bronze_events_queue_url,
            "bronze_events_dlq": settings.bronze_events_dlq,
            "bronze_events_dlq_url": settings.bronze_events_dlq_url,
            "lookback_days": settings.lookback_days,
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "outputs":
        from lakehouse.ops.outputs import collect_outputs, format_exports, write_env_file

        values = collect_outputs(args.tf_dir)
        if args.write_env:
            write_env_file(args.write_env, values)
        if getattr(args, "as_json", False):
            print(json.dumps(values, indent=2))
        else:
            sys.stdout.write(format_exports(values, export=args.export))
        return 0

    if args.command == "dbt":
        from lakehouse.dbt import describe_project

        result = describe_project()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "stream":
        from lakehouse.stream import run_stream

        result = run_stream(count=args.count, mode=args.mode, sink=args.sink)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1

    if args.command == "demo":
        from lakehouse.ops.demo import run_demo

        result = run_demo(count=args.count, mode=args.mode)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1

    if args.command == "quality-dashboard":
        from lakehouse.quality.dashboard import describe_dashboard

        result = describe_dashboard(out=args.out)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "lineage":
        from lakehouse.lineage import describe_lineage

        result = describe_lineage(out=args.out)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "ui":
        from lakehouse.query_ui import describe_ui, serve_html

        out = args.out
        if args.serve and not out:
            out = "build/query-ui.html"
        result = describe_ui(out=out)
        print(json.dumps(result, indent=2))
        if args.serve and result.get("html_path"):
            from pathlib import Path

            serve_html(Path(str(result["html_path"])), host=args.host, port=args.port)
        return 0 if result.get("ok") else 1

    if args.command == "contracts":
        from lakehouse.contract_check import check_all, errors_only, report_issues

        issues = check_all()
        print(json.dumps(report_issues(issues), indent=2))
        return 1 if errors_only(issues) else 0

    if args.command == "security":
        from lakehouse.security import scan_repo

        report = scan_repo()
        print(json.dumps(report.as_dict(), indent=2))
        return 0 if report.ok else 1

    if args.command == "health":
        from lakehouse.ops.health import check_health

        report = check_health()
        print(json.dumps(report, indent=2))
        if report.get("errors"):
            print("WARNING: partial health failure", file=sys.stderr)
        return 0

    if args.command == "seed":
        from lakehouse.ops.seed import seed_bronze

        result = seed_bronze(args.count)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "pipeline":
        from lakehouse.ops.pipeline import run_pipeline

        result = run_pipeline()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "ingest":
        from lakehouse.ingest.bronze_handler import ingest_bronze_event

        result = ingest_bronze_event(None)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") != "failed" else 1

    if args.command == "silver":
        from lakehouse.silver.handler import transform_silver

        result = transform_silver(None)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") != "failed" else 1

    if args.command == "quality":
        from lakehouse.quality.handler import run_quality_gate

        result = run_quality_gate(None)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") not in {"failed", "quality_failed"} else 1

    if args.command == "gold":
        from lakehouse.gold.handler import transform_gold

        result = transform_gold(None)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") != "failed" else 1

    if args.command == "sfn":
        from lakehouse.orchestration.sfn import run_sfn_local

        result = run_sfn_local(None)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") == "succeeded" else 1

    if args.command == "sfn-def":
        from lakehouse.orchestration.sfn import definition_json

        sys.stdout.write(definition_json())
        return 0

    if args.command == "dlq":
        from lakehouse.ops.dlq import list_dlq

        result = list_dlq(max_messages=args.max_messages)
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.command == "redrive":
        from lakehouse.ops.dlq import redrive_dlq

        result = redrive_dlq(max_messages=args.max_messages)
        print(json.dumps(result, indent=2, default=str))
        return 0 if not result.get("errors") else 1

    if args.command == "reprocess":
        from datetime import datetime

        from lakehouse.ops.reprocess import reprocess_gold_window

        as_of = None
        if args.as_of:
            as_of = datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00"))
        result = reprocess_gold_window(
            as_of=as_of,
            lookback_days=args.lookback_days,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") != "failed" else 1

    if args.command == "metrics":
        from lakehouse.metrics import describe_metrics

        result = describe_metrics()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "catalog":
        from lakehouse.catalog import register_catalog

        result = register_catalog()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "partitions":
        from lakehouse.partitions import describe_partitions

        result = describe_partitions()
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.command == "athena":
        from lakehouse.athena import register_athena, run_named_query

        if args.name:
            result = run_named_query(args.name)
        else:
            result = register_athena()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "query":
        from lakehouse.ops.query import query_gold

        result = query_gold()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "runs":
        from lakehouse.ops.runs import list_runs

        result = list_runs()
        print(json.dumps(result, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
