#!/usr/bin/env bash
# Deploy ONLY the frontend to the demo EC2, without downtime.
#
# Caddy bind-mounts ~/virtualos/web/dist. Deleting/recreating that directory
# leaves the container pointing at the deleted inode -> 404 on every page
# (happened 2026-11-13). So we NEVER rm the directory: files are replaced in
# place and stale assets removed afterwards.
#
# Usage (Git Bash): ./deploy/deploy_web.sh
set -euo pipefail

HOST="ubuntu@3.137.22.45"
KEY="$HOME/.ssh/virtualos-demo"
DOMAIN="https://vos.orkiza.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="/tmp/vos-web-$$.tgz"

echo "==> Build"
(cd "$ROOT/web" && VITE_API_BASE="$DOMAIN" npm run build)
EXPECTED="$(ls "$ROOT/web/dist/assets/" | grep -E '^index-.*\.js$')"

echo "==> Upload"
tar czf "$PKG" -C "$ROOT/web/dist" .
scp -q -i "$KEY" "$PKG" "$HOST:/tmp/vos-web.tgz"
rm -f "$PKG"

echo "==> Replace in place (directory inode preserved)"
ssh -i "$KEY" "$HOST" '
  set -e
  D=~/virtualos/web/dist
  mkdir -p "$D"
  STAGE=$(mktemp -d)
  tar xzf /tmp/vos-web.tgz -C "$STAGE" && rm /tmp/vos-web.tgz
  cp -r "$STAGE"/. "$D"/
  # remove assets no longer referenced by the new build
  (cd "$D" && find . -type f | sort) > /tmp/old.txt
  (cd "$STAGE" && find . -type f | sort) > /tmp/new.txt
  comm -23 /tmp/old.txt /tmp/new.txt | (cd "$D" && xargs -r rm -f)
  rm -rf "$STAGE" /tmp/old.txt /tmp/new.txt
'

echo "==> Verify from the SERVER response (not local files)"
SERVED="$(curl -s --max-time 15 "$DOMAIN/" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1 || true)"
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$DOMAIN/")"
if [ "$CODE" = "200" ] && [ "$SERVED" = "$EXPECTED" ]; then
  echo "OK: $DOMAIN -> 200, serving $SERVED"
else
  echo "FAIL: HTTP $CODE, served='$SERVED' expected='$EXPECTED'" >&2
  echo "Recovery: ssh -i $KEY $HOST 'cd ~/virtualos/deploy && sudo docker compose restart caddy'" >&2
  exit 1
fi
