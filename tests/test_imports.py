"""Guard the public package layout so refactors cannot silently break imports."""

from __future__ import annotations

import importlib

PUBLIC_MODULES = [
    "lakehouse",
    "lakehouse.config",
    "lakehouse.aws",
    "lakehouse.models",
    "lakehouse.contracts",
    "lakehouse.contract_check",
    "lakehouse.catalog",
    "lakehouse.partitions",
    "lakehouse.athena",
    "lakehouse.dbt",
    "lakehouse.query_ui",
    "lakehouse.metrics",
    "lakehouse.retention",
    "lakehouse.bronze_retention",
    "lakehouse.silver_retention",
    "lakehouse.bronze_compact",
    "lakehouse.bronze_maintain",
    "lakehouse.silver_compact",
    "lakehouse.silver_maintain",
    "lakehouse.compact",
    "lakehouse.maintain",
    "lakehouse.platform_maintain",
    "lakehouse.quarantine_retention",
    "lakehouse.sla",
    "lakehouse.lineage",
    "lakehouse.release",
    "lakehouse.security",
    "lakehouse.storage",
    "lakehouse.cli",
    "lakehouse.seed",
    "lakehouse.seed.generate",
    "lakehouse.pipeline",
    "lakehouse.pipeline.bronze",
    "lakehouse.pipeline.silver",
    "lakehouse.pipeline.gold",
    "lakehouse.pipeline.quality",
    "lakehouse.pipeline.runs",
    "lakehouse.pipeline.idempotency",
    "lakehouse.ingest",
    "lakehouse.ingest.s3_events",
    "lakehouse.ingest.bronze_handler",
    "lakehouse.silver",
    "lakehouse.silver.handler",
    "lakehouse.gold",
    "lakehouse.gold.handler",
    "lakehouse.quality",
    "lakehouse.quality.gate",
    "lakehouse.quality.handler",
    "lakehouse.quality.dashboard",
    "lakehouse.orchestration",
    "lakehouse.orchestration.sfn",
    "lakehouse.ops",
    "lakehouse.ops.seed",
    "lakehouse.ops.demo",
    "lakehouse.ops.pipeline",
    "lakehouse.ops.outputs",
    "lakehouse.ops.runs",
    "lakehouse.ops.lambda_package",
    "lakehouse.ops.notify",
]


def test_public_modules_import() -> None:
    for name in PUBLIC_MODULES:
        module = importlib.import_module(name)
        assert module is not None


def test_package_version_and_exports() -> None:
    import lakehouse

    assert lakehouse.__version__
    assert hasattr(lakehouse, "Settings")
    assert hasattr(lakehouse, "get_settings")


def test_seed_and_pipeline_reexports() -> None:
    from lakehouse.contracts import load_all_contracts, load_contract
    from lakehouse.ops import expected_notification, package_lambda
    from lakehouse.orchestration import build_definition, run_sfn_local
    from lakehouse.pipeline import (
        bronze_key,
        deterministic_run_id,
        gold_key,
        idempotency_key,
        new_run,
        persist_run,
        quarantine_key,
        run_quality_checks,
        silver_key,
    )
    from lakehouse.quality import evaluate_quality, run_quality_gate
    from lakehouse.seed import generate_events

    assert callable(generate_events)
    assert callable(bronze_key)
    assert callable(silver_key)
    assert callable(quarantine_key)
    assert callable(gold_key)
    assert callable(run_quality_checks)
    assert callable(new_run)
    assert callable(persist_run)
    assert callable(idempotency_key)
    assert callable(deterministic_run_id)
    assert callable(evaluate_quality)
    assert callable(run_quality_gate)
    assert callable(package_lambda)
    assert callable(expected_notification)
    assert callable(load_contract)
    assert callable(load_all_contracts)
    assert callable(build_definition)
    assert callable(run_sfn_local)
