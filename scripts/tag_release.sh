#!/usr/bin/env bash
# Create an annotated vX.Y.Z tag after the hermetic release plan is clean.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-}"
DRY_RUN="${DRY_RUN:-0}"
PYTHON="${PYTHON:-python3}"

cd "$ROOT"

args=()
if [[ -n "$VERSION" ]]; then
  args+=(--version "$VERSION")
fi
if [[ "$DRY_RUN" == "1" ]]; then
  exec "$PYTHON" -m lakehouse release "${args[@]}"
fi
exec "$PYTHON" -m lakehouse release --tag "${args[@]}"
