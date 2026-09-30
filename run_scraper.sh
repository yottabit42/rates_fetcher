#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

TARGETS_FILE="${1:-targets.tsv}"
shift || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting fund scraper run for targets: ${TARGETS_FILE}"
python3 scrape.py "${TARGETS_FILE}" "$@"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fund scraper run completed successfully."
