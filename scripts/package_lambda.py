#!/usr/bin/env python3
"""CLI wrapper around ``lakehouse.ops.lambda_package``.

    python scripts/package_lambda.py
    python scripts/package_lambda.py --out build/lambda/lakehouse.zip --no-vendor
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lakehouse.ops.lambda_package import DEFAULT_BUILD_DIR, DEFAULT_ZIP, package  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_ZIP, help="Zip path")
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument(
        "--no-vendor",
        action="store_true",
        help="Skip pip-install of pydantic (unit tests / already-vendored tree)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    zip_path = package(
        build_dir=args.build_dir,
        zip_path=args.out,
        vendor=not args.no_vendor,
    )
    print(f"wrote {zip_path} ({zip_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
