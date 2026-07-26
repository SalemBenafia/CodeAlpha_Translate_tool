#!/usr/bin/env bash
# Start the server. Any env var from .env.example can be set inline, e.g.
#   PORT=3001 ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "No .venv found — run ./setup.sh first." >&2
  exit 1
fi

exec .venv/bin/python -m app "$@"
