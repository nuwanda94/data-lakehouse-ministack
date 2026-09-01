"""CLI entrypoint for local lakehouse operations."""

from __future__ import annotations

import argparse
import sys

from lakehouse.cli_commands import HANDLERS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lakehouse")
    parser.add_argument("--version", action="store_true", help="Print package version")
    sub = parser.add_subparsers(dest="command", required=False)

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text)

    add("health", "Probe MiniStack S3 + DynamoDB")
    p_seed = add("seed", "Write synthetic commerce events to Bronze")
    p_seed.add_argument("--count", type=int, default=20)
    add("pipeline", "Run Bronze → Silver → quality → Gold locally")
    add("ingest", "Drain Bronze SQS / process pending Bronze objects")
    add("silver", "Cleanse Bronze → Silver")
    add("quality", "Run Silver quality gate")
    add("gold", "Aggregate Silver → Gold metrics")
    add("query", "Print Gold summary")
    add("catalog", "Describe (and best-effort register) Glue Silver/Gold tables")
    add("partitions", "Describe Athena partition projection + discover Hive keys on S3")
    add("metrics", "Describe the CloudWatch metric catalog and in-process buffer")
    p_athena = add("athena", "Describe Athena workgroup + named queries")
    p_athena.add_argument("--name", default=None, help="Named query to start")
    add("runs", "List pipeline runs from DynamoDB")
    add("sfn", "Walk the Step Functions graph locally")
    add("sfn-def", "Print the medallion Amazon States Language definition")
    p_dlq = add("dlq", "Peek the Bronze events dead-letter queue")
    p_dlq.add_argument("--max", type=int, default=10, dest="max_messages")
    p_redrive = add("redrive", "Move Bronze DLQ messages back onto the source events queue")
    p_redrive.add_argument("--max", type=int, default=10, dest="max_messages")
    p_reprocess = add("reprocess", "Rebuild Gold partitions for a late-arriving lookback window")
    p_reprocess.add_argument("--lookback-days", type=int, default=None)
    p_reprocess.add_argument("--as-of", default=None)
    add("dbt", "Parse and lint the transform/dbt Gold project")
    p_ui = add("ui", "Render the Gold query dashboard")
    p_ui.add_argument("--out", default=None)
    p_ui.add_argument("--serve", action="store_true")
    p_ui.add_argument("--host", default="127.0.0.1")
    p_ui.add_argument("--port", type=int, default=8765)
    add("contracts", "Validate zone contracts")
    add("security", "Run security scan helpers")
    add("env", "Print effective environment")
    p_settings = add("settings", "Print resolved Settings")
    p_settings.add_argument("--json", action="store_true", dest="as_json")
    p_outputs = add("outputs", "Print Terraform outputs")
    p_outputs.add_argument("--tf-dir", default=None)
    p_outputs.add_argument("--json", action="store_true", dest="as_json")
    p_stream = add("stream", "Stream producer into Bronze path")
    p_stream.add_argument("--count", type=int, default=5)
    p_stream.add_argument("--mode", default="auto")
    p_stream.add_argument("--sink", default="both")
    p_demo = add("demo", "Run the local demo path")
    p_demo.add_argument("--apply", action="store_true")
    p_demo.add_argument("--mode", default="auto")
    p_demo.add_argument("--count", type=int, default=20)
    p_qdash = add("qdash", "Quality dashboard")
    p_qdash.add_argument("--out", default=None)
    p_qdash2 = add("quality-dashboard", "Render the quality dashboard HTML")
    p_qdash2.add_argument("--out", default=None)
    p_lineage = add("lineage", "Print lineage graph")
    p_lineage.add_argument("--out", default=None)
    add("sla", "Print SLA status")

    def _ret(name: str, help_text: str) -> argparse.ArgumentParser:
        p = add(name, help_text)
        p.add_argument("--retention-days", type=int, default=None)
        p.add_argument("--apply", action="store_true")
        return p

    def _compact(name: str, help_text: str) -> argparse.ArgumentParser:
        p = add(name, help_text)
        p.add_argument("--max-objects", type=int, default=None)
        p.add_argument("--apply", action="store_true")
        return p

    def _maintain(name: str, help_text: str) -> argparse.ArgumentParser:
        p = add(name, help_text)
        p.add_argument("--retention-days", type=int, default=None)
        p.add_argument("--max-objects", type=int, default=None)
        p.add_argument("--apply", action="store_true")
        return p

    _ret("retention", "Plan Gold metric-object expiry")
    _ret("quarantine-retention", "Plan Silver quarantine TTL expiry")
    _ret("silver-retention", "Plan Silver cleaned-event expiry")
    _ret("bronze-retention", "Plan Bronze raw event expiry")
    _compact("compact", "Plan Gold metric-object compact")
    _compact("bronze-compact", "Plan Bronze raw-object compact")
    _compact("silver-compact", "Plan Silver cleaned-event compact")
    _compact("quarantine-compact", "Plan Silver quarantine compact")
    _maintain("maintain", "Gold expire-then-compact")
    _maintain("bronze-maintain", "Bronze expire-then-compact")
    _maintain("silver-maintain", "Silver expire-then-compact")
    _maintain("quarantine-maintain", "Quarantine expire-then-compact")
    p_pm = add("platform-maintain", "Bronze + Silver + Gold expire-then-compact")
    p_pm.add_argument("--retention-days", type=int, default=None)
    p_pm.add_argument("--max-objects", type=int, default=None)
    p_pm.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)
    if args.version:
        from lakehouse import __version__

        print(__version__)
        return 0
    if not args.command:
        parser.print_help()
        return 0
    return dispatch(args)


def dispatch(args: argparse.Namespace) -> int:
    handler = HANDLERS.get(args.command)
    if handler is None:
        print(f"unknown command: {args.command}", file=sys.stderr)
        return 2
    return handler(args)
