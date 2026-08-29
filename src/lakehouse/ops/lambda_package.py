"""Build a deployable Lambda zip containing the lakehouse package.

The zip root looks like::

    lakehouse/...
    pydantic/...   (vendored so MiniStack/AWS runtimes do not need a layer)

Handlers therefore stay ``lakehouse.<zone>.*.handler``.
"""

from __future__ import annotations

import compileall
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_LAKEHOUSE = REPO_ROOT / "src" / "lakehouse"
DEFAULT_BUILD_DIR = REPO_ROOT / "build" / "lambda"
DEFAULT_ZIP = DEFAULT_BUILD_DIR / "lakehouse.zip"

SKIP_DIR_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "tests",
    ".git",
}

HANDLER_MODULES = (
    "lakehouse/ingest/bronze_handler.py",
    "lakehouse/silver/handler.py",
    "lakehouse/quality/handler.py",
    "lakehouse/gold/handler.py",
    "lakehouse/config.py",
)


def copy_lakehouse(dest_root: Path, *, source: Path | None = None) -> Path:
    src = source or SRC_LAKEHOUSE
    target = dest_root / "lakehouse"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        src,
        target,
        ignore=shutil.ignore_patterns(*SKIP_DIR_NAMES, "*.pyc"),
    )
    return target


def vendor_dependencies(dest_root: Path, python: str | None = None) -> None:
    cmd = [
        python or sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--upgrade",
        "--disable-pip-version-check",
        "--target",
        str(dest_root),
        "pydantic>=2.6",
    ]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


def prune_build_dir(dest_root: Path) -> None:
    for path in list(dest_root.rglob("*")):
        if path.is_dir() and path.name in SKIP_DIR_NAMES:
            shutil.rmtree(path, ignore_errors=True)
        elif path.suffix in {".pyc", ".pyo"}:
            path.unlink(missing_ok=True)


def write_zip(dest_root: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(dest_root.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix in {".pyc", ".pyo"}:
                continue
            archive.write(file_path, file_path.relative_to(dest_root).as_posix())
    return zip_path


def package(
    *,
    build_dir: Path = DEFAULT_BUILD_DIR,
    zip_path: Path = DEFAULT_ZIP,
    vendor: bool = True,
    python: str | None = None,
    source: Path | None = None,
) -> Path:
    src = source or SRC_LAKEHOUSE
    if not src.is_dir():
        raise FileNotFoundError(f"missing package at {src}")

    dest_root = build_dir / "package"
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    copy_lakehouse(dest_root, source=src)
    if vendor:
        vendor_dependencies(dest_root, python)
    compileall.compile_dir(str(dest_root / "lakehouse"), quiet=1)
    prune_build_dir(dest_root)
    return write_zip(dest_root, zip_path)


def build_lambda_zip(
    *,
    out: Path | None = None,
    vendor: bool = True,
    build_dir: Path | None = None,
    python: str | None = None,
    source: Path | None = None,
) -> Path:
    """CLI-facing wrapper used by ``scripts/package_lambda.py``.

    Maps ``out`` → ``zip_path`` for the underlying ``package`` helper.
    """

    zip_path = out or DEFAULT_ZIP
    return package(
        build_dir=build_dir or DEFAULT_BUILD_DIR,
        zip_path=zip_path,
        vendor=vendor,
        python=python,
        source=source,
    )
