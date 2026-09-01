"""CLI entrypoint for local lakehouse operations."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _ok(payload: dict[str, Any]) -> int:
    _print(payload)
    return 0 if payload.get("ok", True) else 1


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
    add("outputs", "Print Terraform outputs")
    p_stream = add("stream", "Stream producer into Bronze path")
    p_stream.add_argument("--count", type=int, default=5)
    p_demo = add("demo", "Run the local demo path")
    p_demo.add_argument("--apply", action="store_true")
    p_qdash = add("qdash", "Quality dashboard")
    p_qdash.add_argument("--out", default=None)
    add("lineage", "Print lineage graph")
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
    _maintain("maintain", "Gold expire-then-compact")
    _maintain("bronze-maintain", "Bronze expire-then-compact")
    _maintain("silver-maintain", "Silver expire-then-compact")
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
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "health": _cmd_health,
        "seed": _cmd_seed,
        "pipeline": _cmd_pipeline,
        "ingest": _cmd_ingest,
        "silver": _cmd_silver,
        "quality": _cmd_quality,
        "gold": _cmd_gold,
        "query": _cmd_query,
        "catalog": _cmd_catalog,
        "partitions": _cmd_partitions,
        "metrics": _cmd_metrics,
        "athena": _cmd_athena,
        "runs": _cmd_runs,
        "sfn": _cmd_sfn,
        "sfn-def": _cmd_sfn_def,
        "dlq": _cmd_dlq,
        "redrive": _cmd_redrive,
        "reprocess": _cmd_reprocess,
        "dbt": _cmd_dbt,
        "ui": _cmd_ui,
        "contracts": _cmd_contracts,
        "security": _cmd_security,
        "env": _cmd_env,
        "settings": _cmd_settings,
        "outputs": _cmd_outputs,
        "stream": _cmd_stream,
        "demo": _cmd_demo,
        "qdash": _cmd_qdash,
        "lineage": _cmd_lineage,
        "sla": _cmd_sla,
        "retention": _cmd_retention,
        "quarantine-retention": _cmd_qret,
        "silver-retention": _cmd_sret,
        "bronze-retention": _cmd_bret,
        "compact": _cmd_compact,
        "bronze-compact": _cmd_bcompact,
        "silver-compact": _cmd_scompact,
        "maintain": _cmd_maintain,
        "bronze-maintain": _cmd_bmaintain,
        "silver-maintain": _cmd_smaintain,
        "platform-maintain": _cmd_pmaintain,
    }
    handler = handlers.get(args.command)
    if handler is None:
        print(f"unknown command: {args.command}", file=sys.stderr)
        return 2
    return handler(args)


def _cmd_env(_: argparse.Namespace) -> int:
    from lakehouse.environments import describe_env

    _print(describe_env())
    return 0


def _cmd_settings(args: argparse.Namespace) -> int:
    from lakehouse.config import load_settings

    s = load_settings()
    if getattr(args, "as_json", False):
        _print(s.model_dump() if hasattr(s, "model_dump") else dict(s))
    else:
        _print({k: getattr(s, k, None) for k in dir(s) if not k.startswith("_")})
    return 0


def _cmd_outputs(args: argparse.Namespace) -> int:
    from lakehouse.ops.outputs import load_outputs

    _print(load_outputs())
    return 0


def _cmd_dbt(_: argparse.Namespace) -> int:
    from lakehouse.dbt import describe_dbt

    _print(describe_dbt())
    return 0


def _cmd_stream(args: argparse.Namespace) -> int:
    from lakehouse.stream.producer import produce

    _print(produce(count=args.count))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from lakehouse.ops.demo import run_demo

    result = run_demo(apply=getattr(args, "apply", False))
    _print(result)
    return 0 if result.get("ok", True) else 1


def _cmd_qdash(args: argparse.Namespace) -> int:
    from lakehouse.ops.qdash import render_qdash

    _print(render_qdash(out=getattr(args, "out", None)))
    return 0


def _cmd_lineage(_: argparse.Namespace) -> int:
    from lakehouse.lineage import describe_lineage

    _print(describe_lineage())
    return 0


def _cmd_sla(_: argparse.Namespace) -> int:
    from lakehouse.sla import describe_sla

    _print(describe_sla())
    return 0


def _cmd_retention(args: argparse.Namespace) -> int:
    from lakehouse.retention import describe_retention

    return _ok(
        describe_retention(
            retention_days=args.retention_days,
            apply=args.apply,
        )
    )


def _cmd_qret(args: argparse.Namespace) -> int:
    from lakehouse.quarantine_retention import describe_quarantine_retention

    return _ok(
        describe_quarantine_retention(
            retention_days=args.retention_days,
            apply=args.apply,
        )
    )


def _cmd_bret(args: argparse.Namespace) -> int:
    from lakehouse.bronze_retention import describe_bronze_retention

    return _ok(
        describe_bronze_retention(
            retention_days=args.retention_days,
            apply=args.apply,
        )
    )


def _cmd_sret(args: argparse.Namespace) -> int:
    from lakehouse.silver_retention import describe_silver_retention

    return _ok(
        describe_silver_retention(
            retention_days=args.retention_days,
            apply=args.apply,
        )
    )


def _cmd_compact(args: argparse.Namespace) -> int:
    from lakehouse.compact import describe_compact

    return _ok(
        describe_compact(
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_bcompact(args: argparse.Namespace) -> int:
    from lakehouse.bronze_compact import describe_bronze_compact

    return _ok(
        describe_bronze_compact(
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_scompact(args: argparse.Namespace) -> int:
    from lakehouse.silver_compact import describe_silver_compact

    return _ok(
        describe_silver_compact(
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_maintain(args: argparse.Namespace) -> int:
    from lakehouse.maintain import describe_maintain

    return _ok(
        describe_maintain(
            retention_days=args.retention_days,
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_bmaintain(args: argparse.Namespace) -> int:
    from lakehouse.bronze_maintain import describe_bronze_maintain

    return _ok(
        describe_bronze_maintain(
            retention_days=args.retention_days,
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_smaintain(args: argparse.Namespace) -> int:
    from lakehouse.silver_maintain import describe_silver_maintain

    return _ok(
        describe_silver_maintain(
            retention_days=args.retention_days,
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_pmaintain(args: argparse.Namespace) -> int:
    from lakehouse.platform_maintain import describe_platform_maintain

    return _ok(
        describe_platform_maintain(
            retention_days=args.retention_days,
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_ui(args: argparse.Namespace) -> int:
    from lakehouse.query_ui import render_ui

    result = render_ui(
        out=args.out,
        serve=args.serve,
        host=args.host,
        port=args.port,
    )
    if not args.serve:
        _print(result)
    return 0


def _cmd_contracts(_: argparse.Namespace) -> int:
    from lakehouse.contract_check import check_contracts

    result = check_contracts()
    _print(result)
    return 0 if result.get("ok", True) else 1


def _cmd_security(_: argparse.Namespace) -> int:
    from lakehouse.security import describe_security

    _print(describe_security())
    return 0


def _cmd_health(_: argparse.Namespace) -> int:
    from lakehouse.ops.health import health_check

    result = health_check()
    _print(result)
    return 0 if result.get("ok", True) else 1


def _cmd_seed(args: argparse.Namespace) -> int:
    from lakehouse.seed import seed_events

    _print(seed_events(count=args.count))
    return 0


def _cmd_pipeline(_: argparse.Namespace) -> int:
    from lakehouse.pipeline.runner import run_pipeline

    result = run_pipeline()
    _print(result)
    return 0 if result.get("status") != "failed" else 1


def _cmd_ingest(_: argparse.Namespace) -> int:
    from lakehouse.ingest.handler import run_ingest

    _print(run_ingest())
    return 0


def _cmd_silver(_: argparse.Namespace) -> int:
    from lakehouse.silver.handler import run_silver

    _print(run_silver())
    return 0


def _cmd_quality(_: argparse.Namespace) -> int:
    from lakehouse.quality.handler import run_quality

    result = run_quality()
    _print(result)
    return 0 if result.get("ok", True) else 1


def _cmd_gold(_: argparse.Namespace) -> int:
    from lakehouse.gold.handler import run_gold

    _print(run_gold())
    return 0


def _cmd_sfn(_: argparse.Namespace) -> int:
    from lakehouse.orchestration.sfn import run_sfn_local

    result = run_sfn_local()
    _print(result)
    return 0 if result.get("status") != "failed" else 1


def _cmd_sfn_def(_: argparse.Namespace) -> int:
    from lakehouse.orchestration.sfn import definition_json

    sys.stdout.write(definition_json())
    return 0


def _cmd_dlq(args: argparse.Namespace) -> int:
    from lakehouse.ops.dlq import list_dlq

    _print(list_dlq(max_messages=args.max_messages))
    return 0


def _cmd_redrive(args: argparse.Namespace) -> int:
    from lakehouse.ops.dlq import redrive_dlq

    result = redrive_dlq(max_messages=args.max_messages)
    _print(result)
    return 0 if not result.get("errors") else 1


def _cmd_reprocess(args: argparse.Namespace) -> int:
    from datetime import datetime

    from lakehouse.ops.reprocess import reprocess_gold_window

    as_of = None
    if args.as_of:
        as_of = datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00"))
    result = reprocess_gold_window(as_of=as_of, lookback_days=args.lookback_days)
    _print(result)
    return 0 if result.get("status") != "failed" else 1


def _cmd_metrics(_: argparse.Namespace) -> int:
    from lakehouse.metrics import describe_metrics

    _print(describe_metrics())
    return 0


def _cmd_catalog(_: argparse.Namespace) -> int:
    from lakehouse.catalog import register_catalog

    _print(register_catalog())
    return 0


def _cmd_partitions(_: argparse.Namespace) -> int:
    from lakehouse.partitions import describe_partitions

    _print(describe_partitions())
    return 0


def _cmd_athena(args: argparse.Namespace) -> int:
    from lakehouse.athena import register_athena, run_named_query

    result = run_named_query(args.name) if args.name else register_athena()
    _print(result)
    return 0


def _cmd_query(_: argparse.Namespace) -> int:
    from lakehouse.ops.query import query_gold

    _print(query_gold())
    return 0


def _cmd_runs(_: argparse.Namespace) -> int:
    from lakehouse.ops.runs import list_runs

    _print(list_runs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
