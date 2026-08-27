"""Console entry point: `lakehouse` / `python -m lakehouse`."""

from __future__ import annotations

import argparse
import json
import sys

from lakehouse import __version__, get_settings


def _cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _cmd_config(_: argparse.Namespace) -> int:
    settings = get_settings()
    payload = {
        "version": __version__,
        "endpoint_url": settings.endpoint_url,
        "region": settings.region,
        "bronze_bucket": settings.bronze_bucket,
        "silver_bucket": settings.silver_bucket,
        "gold_bucket": settings.gold_bucket,
        "pipeline_runs_table": settings.pipeline_runs_table,
        "gold_metrics_table": settings.gold_metrics_table,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lakehouse",
        description="Local medallion lakehouse on MiniStack",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="Print package version").set_defaults(func=_cmd_version)
    sub.add_parser("config", help="Print resolved settings as JSON").set_defaults(func=_cmd_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
