"""Guard the public package layout so refactors cannot silently break imports."""

from __future__ import annotations

import importlib

PUBLIC_MODULES = [
    "lakehouse",
    "lakehouse.config",
    "lakehouse.aws",
    "lakehouse.models",
    "lakehouse.cli",
    "lakehouse.seed",
    "lakehouse.seed.generate",
    "lakehouse.pipeline",
    "lakehouse.pipeline.bronze",
    "lakehouse.pipeline.silver",
    "lakehouse.pipeline.gold",
    "lakehouse.pipeline.quality",
    "lakehouse.pipeline.runs",
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
    from lakehouse.pipeline import bronze_key, gold_key, run_quality_checks, silver_key
    from lakehouse.seed import generate_events

    assert callable(generate_events)
    assert callable(bronze_key)
    assert callable(silver_key)
    assert callable(gold_key)
    assert callable(run_quality_checks)
