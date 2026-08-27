#!/usr/bin/env bash
# Wait until MiniStack answers on AWS_ENDPOINT_URL (default localhost:4566).
set -euo pipefail

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
TIMEOUT="${HEALTH_TIMEOUT_SECONDS:-60}"
SLEEP="${HEALTH_POLL_SECONDS:-2}"

deadline=$((SECONDS + TIMEOUT))
echo "Waiting for MiniStack at ${ENDPOINT} (timeout ${TIMEOUT}s)..."

while (( SECONDS < deadline )); do
  if curl -fsS --max-time 2 "${ENDPOINT}" >/dev/null 2>&1; then
    echo "MiniStack is reachable at ${ENDPOINT}"
    exit 0
  fi
  # Some builds only speak AWS APIs; a 400/403 on GET / still means the port is up.
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "${ENDPOINT}" || true)"
  if [[ "${code}" =~ ^[2345][0-9][0-9]$ ]]; then
    echo "MiniStack gateway responded HTTP ${code} at ${ENDPOINT}"
    exit 0
  fi
  sleep "${SLEEP}"
done

echo "ERROR: MiniStack did not become healthy at ${ENDPOINT} within ${TIMEOUT}s." >&2
echo "Hint: run 'make up' and check 'docker compose logs ministack'." >&2
exit 1
