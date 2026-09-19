#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_CMD=()

python_command_is_ready() {
  local -a candidate=("$@")

  env -u PYTHONPATH \
    "${candidate[@]}" \
    -c 'import fastapi, pydantic, uvicorn, yaml' \
    >/dev/null 2>&1
}

if [[ -n "${ELYSIA_DEV_PYTHON:-}" ]]; then
  [[ "$ELYSIA_DEV_PYTHON" = /* && -x "$ELYSIA_DEV_PYTHON" ]] || {
    echo "ELYSIA_DEV_PYTHON must name an absolute executable Python interpreter." >&2
    exit 1
  }

  PYTHON_CMD=("$ELYSIA_DEV_PYTHON")

elif [[ -n "${ELYSIA_DEV_CONDA_ENV:-}" ]]; then
  command -v conda >/dev/null 2>&1 || {
    echo "ELYSIA_DEV_CONDA_ENV was supplied, but conda is unavailable." >&2
    exit 1
  }

  PYTHON_CMD=(conda run -n "$ELYSIA_DEV_CONDA_ENV" python)

elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=("$(command -v python3)")

else
  echo "No candidate Python interpreter is available." >&2
  echo "Set ELYSIA_DEV_PYTHON or ELYSIA_DEV_CONDA_ENV explicitly." >&2
  exit 1
fi

if ! python_command_is_ready "${PYTHON_CMD[@]}"; then
  echo "The selected Python environment is not verified for Elysia source development." >&2
  echo "Required imports: import fastapi, pydantic, uvicorn, yaml" >&2
  echo "Set ELYSIA_DEV_PYTHON or ELYSIA_DEV_CONDA_ENV to a qualified environment." >&2
  echo "Packaged installs record their interpreter separately in python-interpreter." >&2
  exit 1
fi

if [[ "${ELYSIA_DEV_PREFLIGHT_ONLY:-0}" == "1" ]]; then
  echo "Elysia source-development Python preflight passed."
  exit 0
fi

exec env -u PYTHONPATH \
  "${PYTHON_CMD[@]}" -m app.cli.runtime serve --mode source "$@"
