#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="dry-run"
WHEELHOUSE=""
PYTHON_BIN=""

usage() {
  echo "Usage: scripts/install_core.sh [--dry-run|--apply] [--python ABSOLUTE_PATH] [--wheelhouse DIRECTORY]"
  echo "Default is --dry-run. No system packages, models, services, or optional profiles are installed."
}

while (( $# > 0 )); do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    --wheelhouse)
      shift
      [[ $# -gt 0 ]] || { echo "--wheelhouse requires a directory." >&2; exit 2; }
      WHEELHOUSE="$1"
      ;;
    --python)
      shift
      [[ $# -gt 0 ]] || { echo "--python requires an absolute interpreter path." >&2; exit 2; }
      PYTHON_BIN="$1"
      ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

USER_HOME="${HOME:?HOME is required}"
CONFIG_BASE="${XDG_CONFIG_HOME:-$USER_HOME/.config}"
DATA_BASE="${XDG_DATA_HOME:-$USER_HOME/.local/share}"
STATE_BASE="${XDG_STATE_HOME:-$USER_HOME/.local/state}"
CACHE_BASE="${XDG_CACHE_HOME:-$USER_HOME/.cache}"
RUNTIME_BASE="${XDG_RUNTIME_DIR:-$STATE_BASE/elysia/runtime}"

for candidate in "$CONFIG_BASE" "$DATA_BASE" "$STATE_BASE" "$CACHE_BASE" "$RUNTIME_BASE"; do
  [[ "$candidate" = /* ]] || { echo "XDG locations must be absolute." >&2; exit 2; }
done

APP_CONFIG="$CONFIG_BASE/elysia"
APP_DATA="$DATA_BASE/elysia"
APP_STATE="$STATE_BASE/elysia"
APP_CACHE="$CACHE_BASE/elysia"
APP_RUNTIME="${XDG_RUNTIME_DIR:+$RUNTIME_BASE/elysia}"
APP_RUNTIME="${APP_RUNTIME:-$RUNTIME_BASE}"
CORE_RUNTIME="$APP_DATA/runtime"
RELEASE_ID="1.0.0"
RELEASE_DIR="$CORE_RUNTIME/releases/$RELEASE_ID"

echo "Elysia Core user-local install plan"
echo "- application payload: XDG user data"
echo "- user configuration: XDG user config (preserved)"
echo "- logs/receipts: XDG user state (preserved)"
echo "- cache: XDG user cache (preserved)"
echo "- session credential: XDG runtime (generated only when the packaged API starts)"
echo "- optional profiles/models/workers/cloud: not installed or enabled"

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run complete; no files were changed. Use --apply to install the tracked Core payload."
  exit 0
fi

if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
[[ "$PYTHON_BIN" = /* && -x "$PYTHON_BIN" ]] || {
  echo "A valid absolute Python 3 interpreter is required." >&2
  exit 1
}
command -v tar >/dev/null 2>&1 || { echo "tar is required to stage the tracked Core payload." >&2; exit 1; }
if [[ -n "$WHEELHOUSE" ]] && [[ ! -d "$WHEELHOUSE" ]]; then
  echo "The supplied offline wheelhouse does not exist." >&2
  exit 1
fi
if [[ -z "$WHEELHOUSE" ]]; then
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" -c \
    'import fastapi, uvicorn, pydantic, yaml, pwdlib, cryptography, zstandard, PIL, numpy, defusedxml, cairosvg, imageio, pytesseract' \
    || {
      echo "Core Python dependencies are missing. Supply a reviewed offline wheelhouse; no network download was attempted." >&2
      exit 1
    }
fi

umask 077
mkdir -p "$APP_CONFIG" "$APP_DATA" "$APP_STATE" "$APP_CACHE" "$APP_RUNTIME" "$CORE_RUNTIME/bin" "$CORE_RUNTIME/releases"

if [[ ! -d "$RELEASE_DIR" ]]; then
  STAGING_DIR="$CORE_RUNTIME/releases/.staging-$RELEASE_ID-$$"
  trap 'test -n "${STAGING_DIR:-}" && test -d "$STAGING_DIR" && mv "$STAGING_DIR" "$APP_STATE/failed-install-staging-$$" 2>/dev/null || true' EXIT
  mkdir -p "$STAGING_DIR"
  tar -C "$REPO_ROOT" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='config/system/machine_profile.yaml' \
    --exclude='config/models/imageforge_models.yaml' \
    --exclude='config/models/speechforge_models.yaml' \
    --exclude='config/models/videoforge_models.yaml' \
    --exclude='config/workers/*forge_worker.yaml' \
    --exclude='derived/runtime' \
    -cf - app core config derived skills \
    requirements/neurofabric-cpu.txt requirements/neurofabric-cuda.txt \
    scripts/prove_neurofabric_runtime.py \
    sandbox/aider_worker sandbox/command_worker sandbox/fetch_worker \
    sandbox/patch_worker sandbox/searxng_worker workers/pdf \
    | tar -C "$STAGING_DIR" -xf -
  mkdir -p "$STAGING_DIR/packaging"
  mkdir -p "$STAGING_DIR/derived/runtime"
  cp "$REPO_ROOT"/packaging/core_runtime_prompts/*.txt "$STAGING_DIR/derived/runtime/"
  cp "$REPO_ROOT/packaging/public_manifest.yaml" "$STAGING_DIR/packaging/public_manifest.yaml"
  cp "$REPO_ROOT/LICENSE" "$REPO_ROOT/LICENSING.md" "$REPO_ROOT/NOTICE" \
    "$REPO_ROOT/THIRD_PARTY_NOTICES.md" "$REPO_ROOT/MODEL_ASSET_NOTICES.md" \
    "$REPO_ROOT/TRADEMARKS.md" "$REPO_ROOT/README.md" \
    "$REPO_ROOT/requirements/core.txt" "$REPO_ROOT/requirements/THIRD_PARTY_NOTICES.txt" \
    "$STAGING_DIR/"
  cp -R "$REPO_ROOT/LICENSES" "$STAGING_DIR/LICENSES"
  mv "$STAGING_DIR" "$RELEASE_DIR"
  STAGING_DIR=""
  trap - EXIT
fi

cp "$REPO_ROOT/scripts/elysia-api" "$CORE_RUNTIME/bin/elysia-api"
chmod 0700 "$CORE_RUNTIME/bin/elysia-api"
cp "$REPO_ROOT/scripts/manage_qdrant.sh" "$CORE_RUNTIME/bin/elysia-qdrant"
chmod 0700 "$CORE_RUNTIME/bin/elysia-qdrant"
cp "$REPO_ROOT/scripts/manage_neurofabric.sh" "$CORE_RUNTIME/bin/elysia-neurofabric"
chmod 0700 "$CORE_RUNTIME/bin/elysia-neurofabric"
printf '%s\n' "$PYTHON_BIN" >"$CORE_RUNTIME/python-interpreter"
chmod 0600 "$CORE_RUNTIME/python-interpreter"

if [[ -n "$WHEELHOUSE" ]]; then
  if [[ ! -x "$CORE_RUNTIME/venv/bin/python" ]]; then
    "$PYTHON_BIN" -m venv "$CORE_RUNTIME/venv"
  fi
  "$CORE_RUNTIME/venv/bin/python" -m pip install \
    --disable-pip-version-check --no-index --find-links "$WHEELHOUSE" \
    -r "$RELEASE_DIR/core.txt"
fi

LINK_TMP="$CORE_RUNTIME/.current-$RELEASE_ID-$$"
ln -s "releases/$RELEASE_ID" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$CORE_RUNTIME/current"

cat >"$APP_STATE/install-receipt.json" <<EOF
{"contract":"elysia-core-user-install-1.0","version":"$RELEASE_ID","profile":"core","user_data_preserved":true,"network_used":false,"optional_profiles_enabled":false,"raw_paths_exposed":false}
EOF
chmod 0600 "$APP_STATE/install-receipt.json"

echo "Elysia Core payload installed in user-local XDG storage. No optional profile was enabled."
echo "Run scripts/verify_install.sh to inspect readiness."
