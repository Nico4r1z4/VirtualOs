#!/usr/bin/env bash
# One-command deploy to the demo EC2 box.
# Usage: ./deploy.sh <host> [ssh-key-path]
#   <host>: ubuntu@<elastic-ip or domain>
# Requires: web built locally (npm run build) and deploy/.env present ON THE SERVER.

set -euo pipefail

HOST="${1:?usage: ./deploy.sh ubuntu@<ip> [key.pem]}"
KEY="${2:-}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
[ -n "$KEY" ] && SSH_OPTS+=(-i "$KEY")

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building web"
(cd "$ROOT/web" && npm run build)

echo "==> Syncing repo to $HOST"
rsync -az --delete \
  -e "ssh ${SSH_OPTS[*]}" \
  --exclude .git --exclude node_modules --exclude .venv --exclude .data \
  --exclude .env --exclude '*.pem' \
  "$ROOT/" "$HOST:~/virtualos/"

echo "==> Restarting services"
ssh "${SSH_OPTS[@]}" "$HOST" "cd ~/virtualos/deploy && docker compose up -d --build && docker compose ps"

echo "==> Done. Check https://\$DOMAIN/health"
