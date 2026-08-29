#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-status}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
if [[ ! -f "$REPO_ROOT/requirements/neurofabric-cpu.txt" && -e "$SCRIPT_DIR/../current" ]]; then
  REPO_ROOT="$(cd -- "$SCRIPT_DIR/../current" && pwd -P)"
fi
[[ -f "$REPO_ROOT/config/install/locks/neurofabric-cpu-py312.lock.txt" ]] || {
  echo "The exact CPU Neurofabric lock is unavailable beside this lifecycle manager." >&2
  exit 1
}
[[ -f "$REPO_ROOT/config/install/locks/neurofabric-cuda-py312.lock.txt" ]] || {
  echo "The exact CUDA Neurofabric lock is unavailable beside this lifecycle manager." >&2
  exit 1
}
[[ -f "$REPO_ROOT/scripts/prove_neurofabric_runtime.py" ]] || {
  echo "The Neurofabric runtime proof is unavailable beside this lifecycle manager." >&2
  exit 1
}
USER_BASE="${HOME:?A user home is required}"
STATE_BASE="${XDG_STATE_HOME:-$USER_BASE/.local/state}"
RECEIPT_DIR="$STATE_BASE/elysia/install"
OWNERSHIP_RECEIPT="$RECEIPT_DIR/neurofabric-environment.json"

usage() {
  echo "Usage: scripts/manage_neurofabric.sh [status|prove|install-cpu|install-cuda|uninstall]"
  echo "The explicit profile is isolated from packaged Core and never starts a service."
}

case "$ACTION" in
  status|prove|install-cpu|install-cuda|uninstall) ;;
  *) usage >&2; exit 2 ;;
esac

[[ "$STATE_BASE" = /* ]] || { echo "XDG_STATE_HOME must be absolute." >&2; exit 2; }

DATA_BASE="${XDG_DATA_HOME:-$USER_BASE/.local/share}"
COMPONENT_ROOT="$DATA_BASE/elysia/components"
ENV_PREFIX="${ELYSIA_NEUROFABRIC_PREFIX:-$COMPONENT_ROOT/elysia_neurofabric}"
PYTHON_BIN="${ELYSIA_PYTHON312:-$(command -v python3.12 || true)}"
[[ -n "$PYTHON_BIN" && "$PYTHON_BIN" = /* && -x "$PYTHON_BIN" ]] || {
  echo "A supported absolute Python 3.12 interpreter is required." >&2
  exit 1
}
[[ "$ENV_PREFIX" = /* && "$ENV_PREFIX" != "/" && "$ENV_PREFIX" != "$COMPONENT_ROOT" ]] || {
  echo "The Neurofabric environment prefix is unsafe." >&2
  exit 2
}

environment_exists() {
  [[ -x "$ENV_PREFIX/bin/python" ]]
}

status() {
  if ! environment_exists; then
    echo "Neurofabric environment: absent ($ENV_PREFIX)"
    return 1
  fi
  "$ENV_PREFIX/bin/python" -c \
    'import importlib.metadata,json,sys; import torch; print(json.dumps({"python":sys.version.split()[0],"torch":torch.__version__,"torch_cuda_runtime":torch.version.cuda,"cuda_available":torch.cuda.is_available(),"ncps":importlib.metadata.version("ncps")}))'
}

write_receipt() {
  local variant="$1"
  umask 077
  mkdir -p "$RECEIPT_DIR"
  printf '{\n  "contract": "elysia-neurofabric-environment-ownership-v2",\n  "managed_by_elysia": true,\n  "variant": "%s",\n  "environment_id": "elysia_neurofabric",\n  "python": "3.12",\n  "hash_lock": "config/install/locks/neurofabric-%s-py312.lock.txt",\n  "user_data_present": false,\n  "raw_paths_exposed": false\n}\n' \
    "$variant" "$variant" >"$OWNERSHIP_RECEIPT"
  chmod 0600 "$OWNERSHIP_RECEIPT"
}

install_variant() {
  local variant="$1"
  local requirements="$REPO_ROOT/config/install/locks/neurofabric-$variant-py312.lock.txt"
  if [[ "$variant" == "cuda" ]]; then
    command -v nvidia-smi >/dev/null 2>&1 || {
      echo "CUDA installation refused: no NVIDIA driver proof is available." >&2
      exit 1
    }
    python3 - <<'PY'
import subprocess
result = subprocess.run(
    ["nvidia-smi", "--query-gpu=driver_version,memory.total", "--format=csv,noheader,nounits"],
    check=False, capture_output=True, text=True, timeout=10,
)
rows = [line.strip().split(",") for line in result.stdout.splitlines() if line.strip()]
if result.returncode or not rows:
    raise SystemExit("CUDA installation refused: NVIDIA device/driver proof failed.")
major = min(int(row[0].strip().split(".", 1)[0]) for row in rows)
memory = max(int(row[1].strip()) for row in rows)
if major < 580 or memory < 4096:
    raise SystemExit("CUDA installation refused: the driver or available VRAM is below the supported floor.")
PY
  fi
  if environment_exists; then
    INSTALLED_VARIANT="$($ENV_PREFIX/bin/python -c 'import torch; print("cuda" if torch.version.cuda else "cpu")')"
    [[ "$INSTALLED_VARIANT" == "$variant" ]] || {
      echo "Refusing to change an existing Neurofabric variant without explicit uninstall." >&2
      exit 1
    }
  else
    umask 077
    mkdir -p "$COMPONENT_ROOT"
    "$PYTHON_BIN" -m venv "$ENV_PREFIX"
  fi
  env -u PYTHONPATH "$ENV_PREFIX/bin/python" -m pip install \
    --disable-pip-version-check --require-hashes --requirement "$requirements"
  write_receipt "$variant"
  env -u PYTHONPATH "$ENV_PREFIX/bin/python" "$REPO_ROOT/scripts/prove_neurofabric_runtime.py" --expect "$variant"
}

uninstall_managed() {
  [[ -f "$OWNERSHIP_RECEIPT" && ! -L "$OWNERSHIP_RECEIPT" ]] || {
    echo "Refusing to remove an environment without Elysia's exact ownership receipt." >&2
    exit 1
  }
  "$ENV_PREFIX/bin/python" - "$OWNERSHIP_RECEIPT" "$ENV_PREFIX" <<'PY'
import json
from pathlib import Path
import sys

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if receipt.get("contract") != "elysia-neurofabric-environment-ownership-v2":
    raise SystemExit("The Neurofabric ownership receipt contract is invalid.")
if receipt.get("managed_by_elysia") is not True or receipt.get("environment_id") != "elysia_neurofabric":
    raise SystemExit("The Neurofabric ownership receipt does not authorize this exact environment.")
if receipt.get("user_data_present") is not False:
    raise SystemExit("Refusing to remove an environment marked as containing user data.")
PY
  [[ "$ENV_PREFIX" == "$COMPONENT_ROOT/elysia_neurofabric" ]] || {
    echo "Refusing to remove a non-canonical environment path." >&2
    exit 1
  }
  find "$ENV_PREFIX" -depth -mindepth 1 -delete
  rmdir "$ENV_PREFIX"
  mv -- "$OWNERSHIP_RECEIPT" "$OWNERSHIP_RECEIPT.uninstalled"
  echo "The Elysia-owned Neurofabric environment was removed; its content-free ownership receipt was preserved."
}

case "$ACTION" in
  status) status ;;
  prove)
    status >/dev/null
    INSTALLED_VARIANT="$($ENV_PREFIX/bin/python -c 'import torch; print("cuda" if torch.version.cuda else "cpu")')"
    "$ENV_PREFIX/bin/python" "$REPO_ROOT/scripts/prove_neurofabric_runtime.py" --expect "$INSTALLED_VARIANT"
    ;;
  install-cpu) install_variant cpu ;;
  install-cuda) install_variant cuda ;;
  uninstall) uninstall_managed ;;
esac
