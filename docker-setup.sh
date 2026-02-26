#!/bin/bash
# ── OpenClaw API — Docker Setup ─────────────────────────────────────────────
# One-command setup: generates secrets, writes .env, builds & starts everything.
#
# Usage:
#   ./docker-setup.sh          # first-time setup + start
#   ./docker-setup.sh --build  # rebuild images and restart
#   ./docker-setup.sh --down   # stop everything
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

# ── Helpers ──────────────────────────────────────────────────────────────────
info()  { echo "==> $*"; }
warn()  { echo "WARNING: $*" >&2; }

generate_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}

generate_fernet_key() {
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

# Update or insert a key=value in a file
upsert_env() {
  local file="$1" key="$2" value="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    # Only replace if the current value is empty
    if grep -q "^${key}=$" "$file" || grep -q "^${key}=\"\"$" "$file"; then
      sed -i "s|^${key}=.*|${key}=${value}|" "$file"
      info "Generated $key"
    fi
  else
    echo "${key}=${value}" >> "$file"
    info "Added $key"
  fi
}

# ── Handle flags ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--down" ]]; then
  info "Stopping all services ..."
  docker compose -f "$ROOT_DIR/docker-compose.yml" down
  exit 0
fi

# ── Create .env from example if missing ──────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  info "Creating .env from .env.example ..."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# ── Auto-generate secrets if empty ───────────────────────────────────────────
info "Checking secrets ..."

# Gateway token
if ! grep -qP '^OPENCLAW_GATEWAY_TOKEN=.+' "$ENV_FILE" 2>/dev/null || \
   grep -q '^OPENCLAW_GATEWAY_TOKEN=""' "$ENV_FILE" 2>/dev/null; then
  TOKEN="$(generate_token)"
  # Remove any existing line and add fresh
  sed -i '/^OPENCLAW_GATEWAY_TOKEN=/d' "$ENV_FILE"
  echo "OPENCLAW_GATEWAY_TOKEN=${TOKEN}" >> "$ENV_FILE"
  info "Generated OPENCLAW_GATEWAY_TOKEN"
fi

# Fernet key
if ! grep -qP '^FERNET_KEY=.+' "$ENV_FILE" 2>/dev/null || \
   grep -q '^FERNET_KEY=""' "$ENV_FILE" 2>/dev/null; then
  FKEY="$(generate_fernet_key)"
  sed -i '/^FERNET_KEY=/d' "$ENV_FILE"
  echo "FERNET_KEY=${FKEY}" >> "$ENV_FILE"
  info "Generated FERNET_KEY"
fi

# ── Show summary ─────────────────────────────────────────────────────────────
echo ""
info "Configuration:"
echo "    OPENCLAW_GATEWAY_TOKEN = $(grep '^OPENCLAW_GATEWAY_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
echo "    FERNET_KEY             = $(grep '^FERNET_KEY=' "$ENV_FILE" | cut -d= -f2-)"
echo "    POSTGRES               = openclaw:openclaw@postgres:5432/openclaw"
echo "    OpenClaw Gateway       = http://localhost:${OPENCLAW_PORT:-18789}"
echo "    FastAPI                = http://localhost:${APP_PORT:-8001}"
echo ""

# ── Build & Start ────────────────────────────────────────────────────────────
BUILD_FLAG=""
if [[ "${1:-}" == "--build" ]] || [[ ! "$(docker images -q openclaw-api-openclaw 2>/dev/null)" ]]; then
  BUILD_FLAG="--build"
fi

info "Starting services ${BUILD_FLAG:+(with build)} ..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up ${BUILD_FLAG} -d

echo ""
info "All services started!"
echo ""
echo "    OpenClaw Gateway  → http://localhost:${OPENCLAW_PORT:-18789}"
echo "    FastAPI (API)     → http://localhost:${APP_PORT:-8001}"
echo "    FastAPI (docs)    → http://localhost:${APP_PORT:-8001}/docs"
echo ""
echo "    Logs: docker compose logs -f"
echo "    Stop: ./docker-setup.sh --down"
