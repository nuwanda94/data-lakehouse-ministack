"""Package entry point for `python -m lakehouse` and the console script."""

from __future__ import annotations

import argparse
import json
import sys

from lakehouse import __version__, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lakehouse", description="MiniStack lakehouse CLI")
    parser.add_argument("--version", action="store_true", help="Print package version")
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "settings",
            "health",
            "seed",
            "pipeline",
            "query",
            "outputs",
            "ingest",
            "silver",
        ),
        help="Command to run.",
    )
    parser.add_argument("--count", type=int, default=50, help="Events to seed (seed only)")
    parser.add_argument("--tf-dir", default=None, help="Terraform directory (outputs only)")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Prefix KEY=value lines with export (outputs only)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON output (outputs)")
    parser.add_argument("--write-env", default=None, help="Write dotenv file (outputs only)")
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "settings":
        settings = load_settings()
        payload = {
            "aws_endpoint_url": settings.aws_endpoint_url,
            "aws_region": settings.aws_region,
            "bronze_bucket": settings.bronze_bucket,
            "silver_bucket": settings.silver_bucket,
            "gold_bucket": settings.gold_bucket,
            "pipeline_runs_table": settings.pipeline_runs_table,
            "gold_metrics_table": settings.gold_metrics_table,
            "bronze_events_queue": settings.bronze_events_queue,
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "outputs":
        from lakehouse.ops.outputs import collect_outputs, format_exports, write_env_file

        values = collect_outputs(args.tf_dir)
        if args.write_env:
            write_env_file(args.write_env, values)
        if args.as_json:
            print(json.dumps(values, indent=2))
        else:
            sys.stdout.write(format_exports(values, export=args.export))
        return 0

    if args.command == "health":
        from lakehouse.ops.health import check_health

        report = check_health()
        print(json.dumps(report, indent=2))
        if report.get("errors"):
            print("WARNING: partial health failure", file=sys.stderr)
            return 1
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
        from lakehouse.ingest.bronze_handler import drain_bronze_queue

        result = drain_bronze_queue()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "silver":
        from lakehouse.silver.handler import run_silver

        result = run_silver()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "query":
        from lakehouse.ops.query import query_gold

        result = query_gold()
        print(json.dumps(result, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
