#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export ELYSIA_RUNTIME_MODE=test
TEST_PYTHON="${ELYSIA_TEST_PYTHON:-python}"

QA_ROOT="$(mktemp -d /tmp/elysia-pass10d-i-XXXXXXXX)"
case "$QA_ROOT" in
  /tmp/elysia-pass10d-i-*) ;;
  *)
    echo "Refusing an unsafe Pass 10D I QA root." >&2
    exit 2
    ;;
esac

cleanup_qa_root() {
  case "$QA_ROOT" in
    /tmp/elysia-pass10d-i-*) rm -rf -- "$QA_ROOT" ;;
    *) echo "Refusing to clean an unrecognized QA root." >&2 ;;
  esac
}
trap cleanup_qa_root EXIT HUP INT TERM

export ELYSIA_QA_ROOT="$QA_ROOT"
export ELYSIA_QA_RUN_ID="pass10d-i-$(basename "$QA_ROOT")-$$"
export ELYSIA_QA_CANARY="synthetic-gate-zero-$ELYSIA_QA_RUN_ID"
export XDG_CONFIG_HOME="$QA_ROOT/config"
export XDG_DATA_HOME="$QA_ROOT/data"
export XDG_STATE_HOME="$QA_ROOT/state"
export XDG_CACHE_HOME="$QA_ROOT/cache"
export XDG_RUNTIME_DIR="$QA_ROOT/runtime"

mkdir -p \
  "$XDG_CONFIG_HOME" \
  "$XDG_DATA_HOME" \
  "$XDG_STATE_HOME" \
  "$XDG_CACHE_HOME" \
  "$XDG_RUNTIME_DIR"
chmod 700 \
  "$QA_ROOT" \
  "$XDG_CONFIG_HOME" \
  "$XDG_DATA_HOME" \
  "$XDG_STATE_HOME" \
  "$XDG_CACHE_HOME" \
  "$XDG_RUNTIME_DIR"

"$TEST_PYTHON" -m scripts.assert_disposable_xdg

if [ "${1:-}" = "--preflight-only" ]; then
  echo "Pass 10D I disposable-XDG preflight passed; cleanup is armed."
  exit 0
fi

if [ "$#" -eq 0 ]; then
  "$TEST_PYTHON" -m pytest tests
else
  "$TEST_PYTHON" -m pytest "$@"
fi
