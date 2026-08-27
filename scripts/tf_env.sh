#!/usr/bin/env bash
# Compatibility wrapper. Prefer scripts/get_outputs.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "${ROOT}/scripts/get_outputs.sh" "$@"
