#!/usr/bin/env bash
set -euo pipefail

PORT=${PORT:-8787}
HOST=${HOST:-127.0.0.1}
BASE_URL=${BASE_URL:-http://${HOST}:${PORT}}

# Apply local migrations to ensure D1 tables exist.
npx wrangler d1 migrations apply readnweep-db --local

# Start Wrangler dev server in background.
LOG_FILE=$(mktemp)
cleanup() {
  if [[ -n "${WRANGLER_PID:-}" ]]; then
    kill "${WRANGLER_PID}" >/dev/null 2>&1 || true
  fi
  rm -f "${LOG_FILE}"
}
trap cleanup EXIT

npx wrangler dev --local --port "${PORT}" --ip "${HOST}" >"${LOG_FILE}" 2>&1 &
WRANGLER_PID=$!

# Wait for server to be ready.
for _ in $(seq 1 30); do
  if curl -fsS "${BASE_URL}/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if ! kill -0 "${WRANGLER_PID}" >/dev/null 2>&1; then
    echo "Wrangler exited early. Logs:" >&2
    cat "${LOG_FILE}" >&2
    exit 1
  fi
  done

# Run smoke test.
BASE_URL="${BASE_URL}" scripts/smoke_test.sh "${BASE_URL}"
