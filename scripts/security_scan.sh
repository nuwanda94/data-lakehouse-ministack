#!/usr/bin/env bash
# Run hermetic secret scan, then Checkov / Trivy when installed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

echo "==> hermetic lakehouse.security"
"$PYTHON" -m lakehouse security

if command -v checkov >/dev/null 2>&1; then
  echo "==> checkov infra/terraform"
  checkov -d "$ROOT/infra/terraform" --config-file "$ROOT/.checkov.yaml"
else
  echo "==> checkov not installed (CI installs it; local: pip install checkov)"
fi

if command -v trivy >/dev/null 2>&1; then
  echo "==> trivy fs secrets"
  trivy fs --config "$ROOT/trivy.yaml" --scanners secret --exit-code 1 "$ROOT"
else
  echo "==> trivy not installed (CI uses aquasecurity/trivy-action)"
fi

echo "==> security scan complete"
