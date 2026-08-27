#!/usr/bin/env bash
# Fetch Terraform outputs and print KEY=value lines for `eval` / env export.
#
# Usage:
#   eval "$(scripts/get_outputs.sh)"
#   scripts/get_outputs.sh --export
#   scripts/get_outputs.sh --write-env .env.generated
#   python -m lakehouse outputs
#
# Prefers `terraform output -json`, then terraform.tfstate, then documented defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${TF_DIR:-${ROOT}/infra/terraform}"
MODE="plain"
WRITE_ENV=""

usage() {
  cat <<'EOF'
Usage: scripts/get_outputs.sh [--export] [--json] [--write-env PATH] [--tf-dir DIR]

Print lakehouse env vars sourced from Terraform outputs.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --export) MODE="export"; shift ;;
    --json) MODE="json"; shift ;;
    --write-env)
      WRITE_ENV="${2:-}"
      if [[ -z "${WRITE_ENV}" ]]; then
        echo "ERROR: --write-env requires a path" >&2
        exit 2
      fi
      shift 2
      ;;
    --tf-dir)
      TF_DIR="${2:-}"
      if [[ -z "${TF_DIR}" ]]; then
        echo "ERROR: --tf-dir requires a directory" >&2
        exit 2
      fi
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
PY_ARGS=(--tf-dir "${TF_DIR}")
if [[ -n "${WRITE_ENV}" ]]; then
  PY_ARGS+=(--write-env "${WRITE_ENV}")
fi
case "${MODE}" in
  export) PY_ARGS+=(--export) ;;
  json) PY_ARGS+=(--json) ;;
esac

exec python3 -m lakehouse outputs "${PY_ARGS[@]}"
