#!/usr/bin/env bash
# Wait until MiniStack answers on AWS_ENDPOINT_URL (default localhost:4566).
set -euo pipefail

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
TIMEOUT="${HEALTH_TIMEOUT_SECONDS:-90}"
SLEEP="${HEALTH_POLL_SECONDS:-2}"
# Prefer the dedicated health endpoint; fall back to the gateway root.
HEALTH_PATHS=("/_ministack/health" "/_localstack/health" "/")

deadline=$((SECONDS + TIMEOUT))
echo "Waiting for MiniStack at ${ENDPOINT} (timeout ${TIMEOUT}s)..."

while (( SECONDS < deadline )); do
  for path in "${HEALTH_PATHS[@]}"; do
    url="${ENDPOINT}${path}"
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "${url}" 2>/dev/null || true)"
    if [[ "${code}" =~ ^[2345][0-9][0-9]$ ]]; then
      echo "MiniStack is reachable at ${url} (HTTP ${code})"
      exit 0
    fi
  done
  sleep "${SLEEP}"
done

echo "ERROR: MiniStack did not become healthy at ${ENDPOINT} within ${TIMEOUT}s." >&2
echo "Hint: run 'make up' and check 'docker compose logs ministack'." >&2
exit 1
