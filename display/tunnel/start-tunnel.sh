#!/usr/bin/env bash
# start-tunnel.sh — boot the cloudflared tunnel alongside the GM display.
# One-time setup: see docs/REMOTE-PLAY.md (cloudflared login + tunnel create).
set -euo pipefail

DISPLAY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TUNNEL_NAME="${GM_TUNNEL_NAME:-gm-display}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "error: cloudflared not installed (brew install cloudflared)" >&2
  exit 1
fi

# Display must be up first (localhost only — the tunnel is the sole way in).
if ! curl -sf "http://localhost:5001/ping" >/dev/null; then
  echo "display not running — starting it..."
  bash "$DISPLAY_DIR/start-display.sh"
  sleep 2
fi

echo "starting tunnel '$TUNNEL_NAME' → http://localhost:5001"
exec cloudflared tunnel run "$TUNNEL_NAME"
