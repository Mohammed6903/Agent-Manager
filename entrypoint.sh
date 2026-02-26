#!/bin/bash
set -e

# Wait for the OpenClaw gateway to be reachable (the FastAPI app shells out to
# the `openclaw` CLI which needs a running gateway).
echo "==> Waiting for OpenClaw gateway at ${OPENCLAW_GATEWAY_URL:-http://openclaw:18789} ..."
for i in $(seq 1 30); do
  if curl -sf "${OPENCLAW_GATEWAY_URL:-http://openclaw:18789}" >/dev/null 2>&1; then
    echo "    Gateway is up."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "    WARNING: gateway not reachable after 30 s — continuing anyway."
  fi
  sleep 1
done

echo "==> Running database migrations ..."
alembic upgrade head 2>/dev/null || echo "    (skipped — no pending migrations or alembic not configured)"

echo "==> Starting FastAPI on ${SERVER_HOST:-0.0.0.0}:${SERVER_PORT:-8001} ..."
exec python main.py
