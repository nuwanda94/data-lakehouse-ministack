"""Minimal package entry point so `python -m lakehouse` and the console script work."""

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
        choices=("settings",),
        help="Optional command. `settings` prints the resolved configuration.",
    )
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
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
        }
        print(json.dumps(payload, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
