#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
RUNTIME_DIR="$ROOT/.runtime"
REQ_HASH="$(sha256sum "$ROOT/requirements.txt" | awk '{print $1}')"
REQ_HASH_FILE="$RUNTIME_DIR/requirements.sha256"
PYTHON_BIN="python3"

mkdir -p "$RUNTIME_DIR"

if [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
  PYTHON_BIN="$VENV/bin/python"
elif [[ ! -x "$VENV/bin/python" ]]; then
  if python3 -m venv "$VENV" >/dev/null 2>&1; then
    PYTHON_BIN="$VENV/bin/python"
  else
    echo "python3-venv is unavailable; falling back to the system interpreter." >&2
  fi
else
  echo "Existing virtual environment is incomplete; falling back to the system interpreter." >&2
fi

"$PYTHON_BIN" -m pip --disable-pip-version-check install --quiet --upgrade pip

if [[ ! -f "$REQ_HASH_FILE" ]] || [[ "$(cat "$REQ_HASH_FILE")" != "$REQ_HASH" ]]; then
  "$PYTHON_BIN" -m pip --disable-pip-version-check install --quiet -r "$ROOT/requirements.txt"
  printf '%s\n' "$REQ_HASH" > "$REQ_HASH_FILE"
fi

exec "$PYTHON_BIN" "$ROOT/run_local_api.py" "$@"
