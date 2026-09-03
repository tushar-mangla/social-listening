#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/.." && pwd)"
PYTHON_EXE="$PROJECT_ROOT/venv/bin/python"

if [[ ! -x "$PYTHON_EXE" ]]; then
	echo "[run] missing virtual-environment Python: $PYTHON_EXE" >&2
	exit 1
fi

echo "[run] $(date -u +%Y-%m-%dT%H:%M:%SZ) — cycle start" >&2
cd "$HERE/.."
"$PYTHON_EXE" -m listening_loop.run "$@"
echo "[run] cycle done" >&2
