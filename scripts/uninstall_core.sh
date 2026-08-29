#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="dry-run"
case "${1:---dry-run}" in
  --dry-run) MODE="dry-run" ;;
  --apply) MODE="apply" ;;
  --help|-h)
    echo "Usage: scripts/uninstall_core.sh [--dry-run|--apply]"
    exit 0
    ;;
  *) echo "Unknown argument." >&2; exit 2 ;;
esac

USER_HOME="${HOME:?HOME is required}"
CONFIG_BASE="${XDG_CONFIG_HOME:-$USER_HOME/.config}"
DATA_BASE="${XDG_DATA_HOME:-$USER_HOME/.local/share}"
STATE_BASE="${XDG_STATE_HOME:-$USER_HOME/.local/state}"
CORE_RUNTIME="$DATA_BASE/elysia/runtime"
RECOVERY_ROOT="$STATE_BASE/elysia/uninstalled-application"
SEMANTIC_CONFIG="$CONFIG_BASE/elysia/services/qdrant"
NEUROFABRIC_RECEIPT="$STATE_BASE/elysia/install/neurofabric-environment.json"

echo "Elysia Core uninstall plan"
echo "- remove active application payload and fixed API launcher from use"
echo "- stop/remove any explicitly installed Elysia-owned semantic container; leave no service orphan"
echo "- remove an optional Neurofabric environment only when its exact Elysia ownership receipt authorizes it"
echo "- retain config, conversations, projects, artifacts, identity, models, caches, logs, and credentials"
echo "- move application files to a recoverable user-state location; do not delete user data"

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run complete; no files were changed."
  exit 0
fi

if [[ ! -d "$CORE_RUNTIME" ]]; then
  if [[ ! -f "$SEMANTIC_CONFIG/container-runtime" ]]; then
    echo "No installed Core runtime or semantic profile was found; user data remains untouched."
    exit 0
  fi
fi

if [[ -f "$SEMANTIC_CONFIG/container-runtime" ]]; then
  SEMANTIC_MANAGER="$CORE_RUNTIME/bin/elysia-qdrant"
  if [[ ! -x "$SEMANTIC_MANAGER" ]]; then
    SEMANTIC_MANAGER="$REPO_ROOT/scripts/manage_qdrant.sh"
  fi
  [[ -x "$SEMANTIC_MANAGER" ]] || {
    echo "The semantic profile exists but its lifecycle manager is unavailable; refusing to leave an orphan service." >&2
    exit 1
  }
  "$SEMANTIC_MANAGER" uninstall
fi

if [[ -f "$NEUROFABRIC_RECEIPT" ]]; then
  NEUROFABRIC_MANAGER="$CORE_RUNTIME/bin/elysia-neurofabric"
  if [[ ! -x "$NEUROFABRIC_MANAGER" ]]; then
    NEUROFABRIC_MANAGER="$REPO_ROOT/scripts/manage_neurofabric.sh"
  fi
  [[ -x "$NEUROFABRIC_MANAGER" ]] || {
    echo "An Elysia-owned Neurofabric receipt exists but its lifecycle manager is unavailable; refusing an incomplete uninstall." >&2
    exit 1
  }
  "$NEUROFABRIC_MANAGER" uninstall
fi

if [[ ! -d "$CORE_RUNTIME" ]]; then
  echo "The semantic service was removed with no orphan; no Core payload was installed. User data remains untouched."
  exit 0
fi

umask 077
mkdir -p "$RECOVERY_ROOT"
RECOVERY_TARGET="$RECOVERY_ROOT/core-runtime"
if [[ -e "$RECOVERY_TARGET" ]]; then
  echo "A recoverable prior uninstall already exists; refusing to overwrite it." >&2
  exit 1
fi
mv "$CORE_RUNTIME" "$RECOVERY_TARGET"
echo "Application payload moved to recoverable user state. User data was preserved."
