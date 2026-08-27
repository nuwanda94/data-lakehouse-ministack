"""Guard the public package surface so scripts can rely on stable imports."""

from __future__ import annotations


def test_public_exports() -> None:
    import lakehouse

    assert lakehouse.__version__ == "0.1.0"
    assert callable(lakehouse.load_settings)
    assert lakehouse.Settings is not None


def test_subpackages_importable() -> None:
    import lakehouse.aws
    import lakehouse.cli
    import lakehouse.config
    import lakehouse.pipeline
    import lakehouse.quality
    import lakehouse.seed
    import lakehouse.transforms

    assert lakehouse.aws.client is not None
    assert lakehouse.cli.main is not None
