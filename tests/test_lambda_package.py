from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from lakehouse.ops.lambda_package import HANDLER_MODULES, package


def test_package_writes_expected_handlers(tmp_path: Path) -> None:
    zip_path = package(
        build_dir=tmp_path / "build",
        zip_path=tmp_path / "lakehouse.zip",
        vendor=False,
    )
    assert zip_path.is_file()
    assert zip_path.stat().st_size > 0

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    for member in HANDLER_MODULES:
        assert member in names
    assert "lakehouse/__init__.py" in names
    assert not any(name.endswith(".pyc") for name in names)


def test_missing_src_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        package(
            build_dir=tmp_path / "b",
            zip_path=tmp_path / "out.zip",
            vendor=False,
            source=tmp_path / "does-not-exist",
        )
