#!/bin/zsh
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec /usr/bin/python3 "$ROOT/scripts/private_console.py" --host 127.0.0.1 --port 18765
