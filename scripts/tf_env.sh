#!/usr/bin/env bash
# Print Terraform outputs as KEY=value lines suitable for `eval` / env export.
# Falls back to .env.example defaults when terraform has not been applied yet.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${ROOT}/infra/terraform"

emit_defaults() {
  echo "AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL:-http://localhost:4566}"
  echo "AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}"
  echo "BRONZE_BUCKET=${BRONZE_BUCKET:-lakehouse-local-bronze}"
  echo "SILVER_BUCKET=${SILVER_BUCKET:-lakehouse-local-silver}"
  echo "GOLD_BUCKET=${GOLD_BUCKET:-lakehouse-local-gold}"
  echo "PIPELINE_RUNS_TABLE=${PIPELINE_RUNS_TABLE:-lakehouse-local-pipeline-runs}"
  echo "GOLD_METRICS_TABLE=${GOLD_METRICS_TABLE:-lakehouse-local-gold-metrics}"
}

if [[ ! -d "${TF_DIR}/.terraform" ]] && [[ ! -f "${TF_DIR}/terraform.tfstate" ]]; then
  emit_defaults
  exit 0
fi

if ! command -v terraform >/dev/null 2>&1; then
  emit_defaults
  exit 0
fi

cd "${TF_DIR}"
if ! json="$(terraform output -json 2>/dev/null)"; then
  emit_defaults
  exit 0
fi

python3 - "${json}" << 'PY'
import json, sys
raw = sys.argv[1]
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)
mapping = {
    "aws_endpoint_url": "AWS_ENDPOINT_URL",
    "aws_region": "AWS_DEFAULT_REGION",
    "bronze_bucket": "BRONZE_BUCKET",
    "silver_bucket": "SILVER_BUCKET",
    "gold_bucket": "GOLD_BUCKET",
    "pipeline_runs_table": "PIPELINE_RUNS_TABLE",
    "gold_metrics_table": "GOLD_METRICS_TABLE",
}
for tf_name, env_name in mapping.items():
    item = data.get(tf_name) or {}
    value = item.get("value")
    if value:
        print(f"{env_name}={value}")
PY
