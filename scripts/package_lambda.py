#!/usr/bin/env python3
"""Build a Lambda deployment zip from the lakehouse package.

Usage:
    python scripts/package_lambda.py
    python scripts/package_lambda.py --out build/lambda/lakehouse.zip --no-vendor
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without install: add src/ to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lakehouse.ops.lambda_package import build_lambda_zip  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "build" / "lambda" / "lakehouse.zip",
        help="Output zip path",
    )
    parser.add_argument(
        "--no-vendor",
        action="store_true",
        help="Skip vendoring third-party deps (slim package)",
    )
    args = parser.parse_args()
    path = build_lambda_zip(out=args.out, vendor=not args.no_vendor)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
