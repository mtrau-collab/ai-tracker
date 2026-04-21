#!/usr/bin/env bash
# Wrapper for scheduled runs. Invoke as: ./scripts/run_update.sh
# Source .env if present for the API key.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

python -m aai.cli update "$@"
