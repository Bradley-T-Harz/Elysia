#!/usr/bin/env bash
set -euo pipefail

DESKTOP_EXECUTABLE="$1"
PROOF_ROOT="$2"
PORT="$3"
EVIDENCE_DIR="$4"
PACKAGE_LABEL="$5"

mkdir -p \
  "$PROOF_ROOT/config" \
  "$PROOF_ROOT/data" \
  "$PROOF_ROOT/cache" \
  "$PROOF_ROOT/state" \
  "$PROOF_ROOT/runtime" \
  "$EVIDENCE_DIR"
chmod 700 \
  "$PROOF_ROOT/config" \
  "$PROOF_ROOT/data" \
  "$PROOF_ROOT/cache" \
  "$PROOF_ROOT/state" \
  "$PROOF_ROOT/runtime"

export XDG_CONFIG_HOME="$PROOF_ROOT/config"
export XDG_DATA_HOME="$PROOF_ROOT/data"
export XDG_CACHE_HOME="$PROOF_ROOT/cache"
export XDG_STATE_HOME="$PROOF_ROOT/state"
export XDG_RUNTIME_DIR="$PROOF_ROOT/runtime"
export ELYSIA_QA_RUN_ID="pass10d-i-$(basename "$PROOF_ROOT")"
export ELYSIA_LOCAL_API_PORT="$PORT"
export NO_AT_BRIDGE=0
export GTK_MODULES="gail:atk-bridge"
export WEBKIT_DISABLE_COMPOSITING_MODE=1

"$DESKTOP_EXECUTABLE" >"$PROOF_ROOT/app.log" 2>&1 &
app_pid=$!

stop_test_core() {
  local -a core_pids=()
  mapfile -t core_pids < <(
    pgrep -f "^[^ ]*/elysia serve --host 127[.]0[.]0[.]1 --port ${PORT} --mode packaged$" || true
  )
  if ((${#core_pids[@]} == 0)); then
    return
  fi
  kill -TERM -- "${core_pids[@]}" 2>/dev/null || true
  for _ in $(seq 1 30); do
    mapfile -t core_pids < <(
      pgrep -f "^[^ ]*/elysia serve --host 127[.]0[.]0[.]1 --port ${PORT} --mode packaged$" || true
    )
    if ((${#core_pids[@]} == 0)); then
      return
    fi
    sleep 0.1
  done
  kill -KILL -- "${core_pids[@]}" 2>/dev/null || true
}

cleanup() {
  # Headless Xvfb has no window manager to guarantee delivery of the native
  # close request. Terminate only the packaged Core processes bound to this
  # proof's unique loopback port so no disposable sidecar is orphaned.
  stop_test_core
  if kill -0 "$app_pid" 2>/dev/null; then
    kill "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

/usr/bin/python3 "$(dirname "$0")/prove_part2c_graphical.py" \
  "$XDG_RUNTIME_DIR" \
  "$PORT" \
  "$PROOF_ROOT/result.json" \
  "$EVIDENCE_DIR" \
  "$PACKAGE_LABEL"

for _ in $(seq 1 100); do
  if ! kill -0 "$app_pid" 2>/dev/null; then
    wait "$app_pid"
    stop_test_core
    trap - EXIT
    exit 0
  fi
  sleep 0.1
done

# A bare Xvfb display has no window manager to consume WM_DELETE_WINDOW. The
# proof script still sends that native close request; if the headless shell is
# still alive afterward, finish the disposable proof with SIGTERM and verify
# that no packaged Desktop is orphaned.
cleanup
trap - EXIT
exit 0
