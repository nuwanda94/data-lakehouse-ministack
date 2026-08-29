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
    sub.add_parser("runs", help="List pipeline runs from DynamoDB")

    p_settings = sub.add_parser("settings", help="Print resolved settings as JSON")
    p_settings.add_argument("--no-dotenv", action="store_true")

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

    if args.command == "health":
        from lakehouse.ops.health import check_health

        report = check_health()
        print(json.dumps(report, indent=2))
        # Partial service errors are warnings; only fail when nothing is reachable
        # (check_health already raises if both S3 and DynamoDB are down).
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
