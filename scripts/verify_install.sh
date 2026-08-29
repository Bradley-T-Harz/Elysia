#!/usr/bin/env bash
set -Eeuo pipefail

USER_HOME="${HOME:?HOME is required}"
DATA_BASE="${XDG_DATA_HOME:-$USER_HOME/.local/share}"
CORE_RUNTIME="$DATA_BASE/elysia/runtime"
PAYLOAD_ROOT="$CORE_RUNTIME/current"
INTERPRETER_RECORD="$CORE_RUNTIME/python-interpreter"

if [[ ! -d "$PAYLOAD_ROOT/app" ]]; then
  echo "Elysia Core payload is not installed in XDG user data." >&2
  exit 1
fi

if [[ -x "$CORE_RUNTIME/venv/bin/python" ]]; then
  PYTHON_BIN="$CORE_RUNTIME/venv/bin/python"
elif [[ -f "$INTERPRETER_RECORD" ]]; then
  IFS= read -r PYTHON_BIN <"$INTERPRETER_RECORD"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
[[ "$PYTHON_BIN" = /* && -x "$PYTHON_BIN" ]] || {
  echo "The recorded Elysia Python interpreter is unavailable. Rerun the Core installer with --python." >&2
  exit 1
}

export PYTHONPATH="$PAYLOAD_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$PAYLOAD_ROOT"
exec "$PYTHON_BIN" -m app.cli.doctor --probe-local-services --record "$@"
