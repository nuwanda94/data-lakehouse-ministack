"""CLI command implementations imported by lakehouse.cli."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _ok(payload: dict[str, Any]) -> int:
    _print(payload)
    return 0 if payload.get("ok", True) else 1


def _cmd_gqmaintain(args: argparse.Namespace) -> int:
    from lakehouse.gold_quarantine_maintain import describe_gold_quarantine_maintain

    return _ok(
        describe_gold_quarantine_maintain(
            retention_days=getattr(args, "retention_days", None),
            max_objects=getattr(args, "max_objects", None),
            apply=getattr(args, "apply", False),
        )
    )


def _cmd_gqret(args: argparse.Namespace) -> int:
    from lakehouse.gold_quarantine_retention import describe_gold_quarantine_retention

    return _ok(
        describe_gold_quarantine_retention(
            retention_days=args.retention_days,
            apply=args.apply,
        )
    )


def _cmd_gqcompact(args: argparse.Namespace) -> int:
    from lakehouse.gold_quarantine_compact import describe_gold_quarantine_compact

    return _ok(
        describe_gold_quarantine_compact(
            max_objects=getattr(args, "max_objects", None),
            apply=getattr(args, "apply", False),
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


def _cmd_qcompact(args: argparse.Namespace) -> int:
    from lakehouse.quarantine_compact import describe_quarantine_compact

    return _ok(
        describe_quarantine_compact(
            max_objects=getattr(args, "max_objects", None),
            apply=getattr(args, "apply", False),
        )
    )


def _cmd_qmaintain(args: argparse.Namespace) -> int:
    from lakehouse.quarantine_maintain import describe_quarantine_maintain

    return _ok(
        describe_quarantine_maintain(
            retention_days=getattr(args, "retention_days", None),
            max_objects=getattr(args, "max_objects", None),
            apply=getattr(args, "apply", False),
        )
    )


def _cmd_retention(args: argparse.Namespace) -> int:
    from lakehouse.retention import describe_retention

    return _ok(describe_retention(retention_days=args.retention_days, apply=args.apply))


def _cmd_compact(args: argparse.Namespace) -> int:
    from lakehouse.compact import describe_compact

    return _ok(describe_compact(max_objects=args.max_objects, apply=args.apply))


def _cmd_maintain(args: argparse.Namespace) -> int:
    from lakehouse.maintain import describe_maintain

    return _ok(
        describe_maintain(
            retention_days=args.retention_days,
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_bret(args: argparse.Namespace) -> int:
    from lakehouse.bronze_retention import describe_bronze_retention

    return _ok(describe_bronze_retention(retention_days=args.retention_days, apply=args.apply))


def _cmd_bcompact(args: argparse.Namespace) -> int:
    from lakehouse.bronze_compact import describe_bronze_compact

    return _ok(describe_bronze_compact(max_objects=args.max_objects, apply=args.apply))


def _cmd_bmaintain(args: argparse.Namespace) -> int:
    from lakehouse.bronze_maintain import describe_bronze_maintain

    return _ok(
        describe_bronze_maintain(
            retention_days=args.retention_days,
            max_objects=args.max_objects,
            apply=args.apply,
        )
    )


def _cmd_sret(args: argparse.Namespace) -> int:
    from lakehouse.silver_retention import describe_silver_retention

    return _ok(describe_silver_retention(retention_days=args.retention_days, apply=args.apply))


def _cmd_scompact(args: argparse.Namespace) -> int:
    from lakehouse.silver_compact import describe_silver_compact

    return _ok(describe_silver_compact(max_objects=args.max_objects, apply=args.apply))


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

    return _ok(describe_platform_maintain(apply=getattr(args, "apply", False)))


def _cmd_health(_: argparse.Namespace) -> int:
    from lakehouse.ops.health import check_health

    result = check_health()
    result.setdefault("ok", bool(result.get("s3_ok") and result.get("dynamodb_ok")))
    return _ok(result)


def _cmd_seed(args: argparse.Namespace) -> int:
    from lakehouse.ops.seed import seed_bronze

    return _ok(seed_bronze(count=args.count))


def _cmd_pipeline(_: argparse.Namespace) -> int:
    from lakehouse.ops.pipeline import run_pipeline

    result = run_pipeline()
    result.setdefault("ok", result.get("status") != "failed")
    return _ok(result)


def _cmd_ingest(_: argparse.Namespace) -> int:
    from lakehouse.ingest.bronze_handler import drain_bronze_queue

    result = drain_bronze_queue()
    result.setdefault("ok", True)
    return _ok(result)


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


def _cmd_query(_: argparse.Namespace) -> int:
    from lakehouse.ops.query import query_gold

    _print(query_gold())
    return 0


def _cmd_catalog(_: argparse.Namespace) -> int:
    from lakehouse.catalog import describe_catalog

    return _ok(describe_catalog())


def _cmd_partitions(_: argparse.Namespace) -> int:
    from lakehouse.partitions import describe_partitions

    _print(describe_partitions())
    return 0


def _cmd_metrics(_: argparse.Namespace) -> int:
    from lakehouse.metrics import describe_metrics

    _print(describe_metrics())
    return 0


def _cmd_athena(args: argparse.Namespace) -> int:
    from lakehouse.athena import get_named_query, named_queries, register_athena, run_named_query

    if args.name:
        try:
            live = run_named_query(args.name)
            if isinstance(live, dict) and live:
                live.setdefault("ok", True)
                return _ok(live)
        except Exception:
            pass
        q = get_named_query(args.name)
        return _ok({"ok": True, "name": q.name, q.name: q.sql, "sql": q.sql})
    payload = register_athena()
    payload["named_queries"] = [q.name for q in named_queries()]
    for q in named_queries():
        payload.setdefault(q.name, q.sql)
    payload.setdefault("ok", True)
    return _ok(payload)


def _cmd_runs(_: argparse.Namespace) -> int:
    from lakehouse.ops.runs import list_runs

    _print(list_runs())
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


def _cmd_dbt(_: argparse.Namespace) -> int:
    from lakehouse.dbt import describe_project

    return _ok(describe_project())


def _cmd_ui(args: argparse.Namespace) -> int:
    from pathlib import Path

    from lakehouse.query_ui import describe_ui, serve_html

    result = describe_ui(out=args.out)
    if args.serve:
        html_path = result.get("html_path") or args.out
        if not html_path:
            raise SystemExit("ui --serve requires --out")
        serve_html(Path(html_path), host=args.host, port=args.port)
        return 0
    return _ok(result)


def _cmd_contracts(_: argparse.Namespace) -> int:
    from lakehouse.contract_check import check_all, report_issues

    return _ok(report_issues(check_all()))


def _cmd_security(_: argparse.Namespace) -> int:
    from lakehouse.security import scan_repo

    return _ok(scan_repo().as_dict())


def _cmd_env(_: argparse.Namespace) -> int:
    from lakehouse.environments import describe_environment

    payload = describe_environment()
    current = payload.get("current") or {}
    merged = {**current, **payload}
    _print(merged)
    return 0


def _cmd_settings(args: argparse.Namespace) -> int:
    from lakehouse.config import load_settings

    s = load_settings()
    payload = s.as_dict() if hasattr(s, "as_dict") else dict(s)
    _print(payload)
    return 0


def _cmd_outputs(args: argparse.Namespace) -> int:
    from lakehouse.ops.outputs import collect_outputs, format_exports

    values = collect_outputs(getattr(args, "tf_dir", None))
    if getattr(args, "as_json", False):
        _print(values)
        return 0
    print(format_exports(values, export=getattr(args, "export", False)), end="")
    return 0


def _cmd_stream(args: argparse.Namespace) -> int:
    from lakehouse.stream.path import run_stream

    return _ok(
        run_stream(
            getattr(args, "count", 20),
            mode=getattr(args, "mode", "auto"),
            sink=getattr(args, "sink", "both"),
        )
    )


def _cmd_demo(args: argparse.Namespace) -> int:
    from lakehouse.ops.demo import run_demo

    return _ok(run_demo(count=getattr(args, "count", 20), mode=getattr(args, "mode", "auto")))


def _cmd_qdash(args: argparse.Namespace) -> int:
    from lakehouse.quality.dashboard import describe_dashboard

    return _ok(describe_dashboard(out=getattr(args, "out", None)))


def _cmd_quality_dashboard(args: argparse.Namespace) -> int:
    from lakehouse.quality.dashboard import describe_dashboard

    return _ok(describe_dashboard(out=getattr(args, "out", None)))


def _cmd_lineage(args: argparse.Namespace) -> int:
    from lakehouse.lineage import describe_lineage

    return _ok(
        describe_lineage(
            out=getattr(args, "out", None),
            cleanse_floor=getattr(args, "cleanse_floor", None),
        )
    )


def _cmd_sla(args: argparse.Namespace) -> int:
    from lakehouse.sla import describe_sla

    return _ok(describe_sla(max_age_hours=getattr(args, "max_age_hours", None)))
