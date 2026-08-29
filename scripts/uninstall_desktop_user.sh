#!/usr/bin/env bash
set -Eeuo pipefail

MODE="dry-run"
case "${1:---dry-run}" in
  --dry-run) MODE="dry-run" ;;
  --apply) MODE="apply" ;;
  --help|-h)
    echo "Usage: scripts/uninstall_desktop_user.sh [--dry-run|--apply]"
    echo "Removes only Elysia-owned user-local Desktop payload/launchers while preserving all XDG profiles, Memory, projects, conversations, models, settings, and receipts."
    exit 0
    ;;
  *) echo "Unknown argument." >&2; exit 2 ;;
esac

USER_HOME="${HOME:?HOME is required}"
DATA_BASE="${XDG_DATA_HOME:-$USER_HOME/.local/share}"
STATE_BASE="${XDG_STATE_HOME:-$USER_HOME/.local/state}"
LIB_ROOT="$USER_HOME/.local/lib/elysia"
STABLE_LAUNCHER="$USER_HOME/.local/bin/elysia-desktop"
STANDARD_ENTRY="$DATA_BASE/applications/Elysia.desktop"
ICON="$DATA_BASE/icons/hicolor/128x128/apps/elysia-desktop.png"
RECEIPT_ROOT="$STATE_BASE/elysia"
INSTALL_RECEIPT="$RECEIPT_ROOT/desktop-install-receipt.json"
MANAGED_ENTRIES="$RECEIPT_ROOT/desktop-managed-entries.txt"
RECOVERY_ROOT="$RECEIPT_ROOT/uninstalled-desktop"

[[ "$USER_HOME" = /* && "$DATA_BASE" = /* && "$STATE_BASE" = /* ]] || {
  echo "HOME and XDG locations must be absolute." >&2
  exit 2
}
[[ -f "$INSTALL_RECEIPT" && ! -L "$INSTALL_RECEIPT" ]] || {
  echo "No safe Elysia-owned user-local Desktop install receipt exists; refusing ambiguous removal." >&2
  exit 1
}

echo "Elysia Desktop user-local uninstall plan"
echo "- move the Elysia-owned immutable application payload and generated launchers to private recoverable state"
echo "- preserve every XDG account, profile, Memory, project, conversation, model, setting, cache, credential, and receipt"
echo "- do not touch system .deb packages, AppImage files outside this managed install, or unreceipted desktop entries"
if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run complete; no files were changed."
  exit 0
fi

umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
TARGET="$RECOVERY_ROOT/$STAMP"
mkdir -p "$TARGET"

move_if_owned() {
  local source="$1"
  local label="$2"
  if [[ -e "$source" || -L "$source" ]]; then
    mv "$source" "$TARGET/$label"
  fi
}

move_if_owned "$LIB_ROOT" "application-runtime"
if [[ -f "$STABLE_LAUNCHER" && ! -L "$STABLE_LAUNCHER" ]] \
  && grep -Fq '.local/lib/elysia/current/usr/bin/elysia-desktop' "$STABLE_LAUNCHER"; then
  move_if_owned "$STABLE_LAUNCHER" "elysia-desktop-launcher"
fi

if [[ -f "$MANAGED_ENTRIES" && ! -L "$MANAGED_ENTRIES" ]]; then
  entry_index=0
  while IFS= read -r entry; do
    [[ "$entry" = "$USER_HOME"/* || "$entry" = "$STANDARD_ENTRY" ]] || {
      echo "A managed desktop-entry receipt escaped the current user scope; removal stopped." >&2
      exit 1
    }
    if [[ -f "$entry" && ! -L "$entry" ]] && grep -Fq "$STABLE_LAUNCHER" "$entry"; then
      move_if_owned "$entry" "desktop-entry-$entry_index.desktop"
    fi
    entry_index=$((entry_index + 1))
  done <"$MANAGED_ENTRIES"
fi
move_if_owned "$ICON" "elysia-desktop.png"

cat >"$RECEIPT_ROOT/desktop-uninstall-receipt.json" <<EOF
{"contract":"elysia-desktop-user-uninstall-1.0","application_payload_removed":true,"recoverable":true,"user_data_preserved":true,"identity_memory_projects_conversations_deleted":false,"external_appimage_removed":false,"system_package_removed":false,"raw_paths_exposed":false}
EOF
chmod 0600 "$RECEIPT_ROOT/desktop-uninstall-receipt.json"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DATA_BASE/applications" >/dev/null 2>&1 || true
fi
echo "Elysia-owned user-local Desktop application files moved to recoverable private state. User data was preserved."
