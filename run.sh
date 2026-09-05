#!/usr/bin/env bash
# Start RBLXX on the local network.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 main.py "$@"
