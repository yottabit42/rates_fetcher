#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PORT="${1:-${INT_PORT:-57275}}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting secure fund rates server on port ${PORT}..."
exec python3 server.py "${PORT}"
