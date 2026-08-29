#!/usr/bin/env bash
set -Eeuo pipefail

MODE="dry-run"
DEB_PATH=""
ROLLBACK_RELEASE=""
SHORTCUT_DIRS=()

usage() {
  echo "Usage: scripts/install_desktop_user.sh [--dry-run|--apply] (--deb ABSOLUTE_PATH | --rollback-release 12_HEX_ID) [--shortcut-dir ABSOLUTE_DIRECTORY ...]"
  echo "Installs/repairs one digest-keyed user-local Desktop payload or atomically selects one verified prior payload."
}

while (( $# > 0 )); do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    --deb)
      shift
      [[ $# -gt 0 ]] || { echo "--deb requires an absolute path." >&2; exit 2; }
      DEB_PATH="$1"
      ;;
    --rollback-release)
      shift
      [[ $# -gt 0 ]] || { echo "--rollback-release requires a 12-hex release identity." >&2; exit 2; }
      ROLLBACK_RELEASE="$1"
      ;;
    --shortcut-dir)
      shift
      [[ $# -gt 0 ]] || { echo "--shortcut-dir requires an absolute directory." >&2; exit 2; }
      SHORTCUT_DIRS+=("$1")
      ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

USER_HOME="${HOME:?HOME is required}"
DATA_BASE="${XDG_DATA_HOME:-$USER_HOME/.local/share}"
STATE_BASE="${XDG_STATE_HOME:-$USER_HOME/.local/state}"
LIB_ROOT="$USER_HOME/.local/lib/elysia"
BIN_ROOT="$USER_HOME/.local/bin"
APP_ROOT="$DATA_BASE/applications"
ICON_ROOT="$DATA_BASE/icons/hicolor/128x128/apps"
STABLE_LAUNCHER="$BIN_ROOT/elysia-desktop"
STANDARD_ENTRY="$APP_ROOT/Elysia.desktop"

[[ "$USER_HOME" = /* && "$DATA_BASE" = /* && "$STATE_BASE" = /* ]] || {
  echo "HOME and XDG locations must be absolute." >&2
  exit 2
}
if [[ -n "$DEB_PATH" && -n "$ROLLBACK_RELEASE" ]] || [[ -z "$DEB_PATH" && -z "$ROLLBACK_RELEASE" ]]; then
  echo "Select exactly one of --deb or --rollback-release." >&2
  exit 2
fi
if [[ -n "$DEB_PATH" ]]; then
  [[ "$DEB_PATH" = /* && -f "$DEB_PATH" ]] || {
    echo "--deb must name an existing absolute Debian package path." >&2
    exit 2
  }
else
  [[ "$ROLLBACK_RELEASE" =~ ^[0-9a-f]{12}$ ]] || {
    echo "--rollback-release must be exactly 12 lowercase hexadecimal characters." >&2
    exit 2
  }
fi
for directory in "${SHORTCUT_DIRS[@]}"; do
  [[ "$directory" = "$USER_HOME" || "$directory" = "$USER_HOME"/* ]] || {
    echo "Shortcut directories must remain inside the current user's home directory." >&2
    exit 2
  }
done

RELEASES_ROOT="$LIB_ROOT/releases"
CURRENT_LINK="$LIB_ROOT/current"
RECEIPT_ROOT="$STATE_BASE/elysia"
RELEASE_RECEIPT_ROOT="$RECEIPT_ROOT/desktop-releases"
RECOVERY_ROOT="$RECEIPT_ROOT/recoverable-desktop-payloads"
if [[ -n "$DEB_PATH" ]]; then
  command -v dpkg-deb >/dev/null 2>&1 || { echo "dpkg-deb is required." >&2; exit 1; }
  command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum is required." >&2; exit 1; }
  PACKAGE_SHA256="$(sha256sum "$DEB_PATH" | awk '{print $1}')"
  [[ "$PACKAGE_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "The package digest is invalid." >&2; exit 1; }
  RELEASE_ID="${PACKAGE_SHA256:0:12}"
  OPERATION="install_or_repair"
else
  PACKAGE_SHA256=""
  RELEASE_ID="$ROLLBACK_RELEASE"
  OPERATION="rollback"
fi
RELEASE_ROOT="$RELEASES_ROOT/$RELEASE_ID"

echo "Elysia Desktop user-local install plan"
echo "- one immutable release payload"
echo "- one stable current-release link"
echo "- one stable launcher under the user-local binary directory"
echo "- one standard freedesktop application entry"
echo "- optional convenience entries converge on the same launcher"
echo "- existing Elysia config, data, state, and runtime stores are preserved"
if [[ "$OPERATION" == "rollback" ]]; then
  echo "- operation: atomically select prior verified user-local release $RELEASE_ID"
else
  echo "- operation: install or repair exact package-owned bytes"
  echo "- package digest: $PACKAGE_SHA256"
fi

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run complete; no files were changed. Use --apply after reviewing the plan."
  exit 0
fi

umask 077
mkdir -p "$RELEASES_ROOT" "$BIN_ROOT" "$APP_ROOT" "$ICON_ROOT" "$RECEIPT_ROOT" "$RELEASE_RECEIPT_ROOT" "$RECOVERY_ROOT"

if [[ "$OPERATION" == "rollback" ]]; then
  [[ -d "$RELEASE_ROOT" && ! -L "$RELEASE_ROOT" ]] || {
    echo "The selected prior user-local release does not exist safely." >&2
    exit 1
  }
  [[ -f "$RELEASE_RECEIPT_ROOT/$RELEASE_ID.json" && ! -L "$RELEASE_RECEIPT_ROOT/$RELEASE_ID.json" ]] || {
    echo "The selected prior release has no Elysia ownership/integrity receipt." >&2
    exit 1
  }
else
  STAGING_ROOT="$RELEASES_ROOT/.staging-$RELEASE_ID-$$"
  FAILED_STAGING="$RECEIPT_ROOT/failed-desktop-install-$RELEASE_ID-$$"
  trap 'if [[ -n "${STAGING_ROOT:-}" && -d "$STAGING_ROOT" ]]; then mv "$STAGING_ROOT" "$FAILED_STAGING" 2>/dev/null || true; fi' EXIT
  mkdir -p "$STAGING_ROOT"
  dpkg-deb -x "$DEB_PATH" "$STAGING_ROOT"
  [[ -x "$STAGING_ROOT/usr/bin/elysia-desktop" ]] || {
    echo "The Debian package does not contain the Elysia Desktop executable." >&2
    exit 1
  }
  [[ -x "$STAGING_ROOT/usr/bin/elysia" ]] || {
    echo "The Debian package does not contain the fixed Elysia Core sidecar." >&2
    exit 1
  }
  if [[ -d "$RELEASE_ROOT" && ! -L "$RELEASE_ROOT" ]]; then
    if diff -qr --no-dereference "$STAGING_ROOT" "$RELEASE_ROOT" >/dev/null; then
      find "$STAGING_ROOT" -depth -delete
    else
      RECOVERY_TARGET="$RECOVERY_ROOT/$RELEASE_ID-$(date -u +%Y%m%dT%H%M%SZ)-$$"
      mv "$RELEASE_ROOT" "$RECOVERY_TARGET"
      mv "$STAGING_ROOT" "$RELEASE_ROOT"
      OPERATION="repair"
    fi
  else
    [[ ! -e "$RELEASE_ROOT" ]] || { echo "The release target exists but is not a safe directory." >&2; exit 1; }
    mv "$STAGING_ROOT" "$RELEASE_ROOT"
    OPERATION="install"
  fi
  STAGING_ROOT=""
  trap - EXIT
  cat >"$RELEASE_RECEIPT_ROOT/$RELEASE_ID.json" <<EOF
{"contract":"elysia-desktop-user-release-1.0","package_sha256":"$PACKAGE_SHA256","release_id":"$RELEASE_ID","package_owned_payload":true,"user_data_present":false}
EOF
  chmod 0600 "$RELEASE_RECEIPT_ROOT/$RELEASE_ID.json"
fi
[[ -x "$RELEASE_ROOT/usr/bin/elysia-desktop" ]] || {
  echo "The selected Elysia release is missing its Desktop executable." >&2
  exit 1
}
[[ -x "$RELEASE_ROOT/usr/bin/elysia" ]] || {
  echo "The selected Elysia release is missing its fixed Core sidecar." >&2
  exit 1
}

LINK_TEMP="$LIB_ROOT/.current-$RELEASE_ID-$$"
ln -s "releases/$RELEASE_ID" "$LINK_TEMP"
mv -Tf "$LINK_TEMP" "$CURRENT_LINK"

LAUNCHER_TEMP="$BIN_ROOT/.elysia-desktop-$RELEASE_ID-$$"
cat >"$LAUNCHER_TEMP" <<'EOF'
#!/usr/bin/env sh
set -eu
USER_HOME="${HOME:?HOME is required}"
TARGET="$USER_HOME/.local/lib/elysia/current/usr/bin/elysia-desktop"
if [ ! -x "$TARGET" ]; then
  echo "The canonical Elysia Desktop installation is unavailable." >&2
  exit 1
fi
exec env \
  -u PYTHONPATH \
  -u LD_LIBRARY_PATH \
  -u CONDA_PREFIX \
  -u CONDA_DEFAULT_ENV \
  -u ELYSIA_LOCAL_API_PORT \
  "$TARGET" "$@"
EOF
chmod 0700 "$LAUNCHER_TEMP"
if [[ -e "$STABLE_LAUNCHER" ]] && ! cmp -s "$LAUNCHER_TEMP" "$STABLE_LAUNCHER"; then
  LAUNCHER_BACKUP="${STABLE_LAUNCHER}.pre-elysia-${RELEASE_ID}"
  if [[ ! -e "$LAUNCHER_BACKUP" ]]; then
    cp -a "$STABLE_LAUNCHER" "$LAUNCHER_BACKUP"
  fi
fi
mv -f "$LAUNCHER_TEMP" "$STABLE_LAUNCHER"

PACKAGE_ICON="$CURRENT_LINK/usr/share/icons/hicolor/128x128/apps/elysia-desktop.png"
[[ -f "$PACKAGE_ICON" ]] || { echo "The Debian package icon is unavailable." >&2; exit 1; }
install -m 0644 "$PACKAGE_ICON" "$ICON_ROOT/elysia-desktop.png"

ENTRY_TEMP="$RECEIPT_ROOT/generated-desktop-entry-$RELEASE_ID-$$.desktop"
cat >"$ENTRY_TEMP" <<EOF
[Desktop Entry]
Categories=Office;
Comment=Local-first governed AI desktop application.
Exec=$STABLE_LAUNCHER
TryExec=$STABLE_LAUNCHER
StartupWMClass=elysia-desktop
Icon=elysia-desktop
Name=Elysia
Terminal=false
Type=Application
EOF
chmod 0755 "$ENTRY_TEMP"
if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$ENTRY_TEMP"
fi

preserve_and_install_entry() {
  local target="$1"
  local backup="${target}.pre-elysia-${RELEASE_ID}"
  mkdir -p "$(dirname "$target")"
  if [[ -e "$target" ]] && ! cmp -s "$ENTRY_TEMP" "$target"; then
    if [[ ! -e "$backup" ]]; then
      cp -a "$target" "$backup"
    fi
  fi
  install -m 0755 "$ENTRY_TEMP" "$target"
  if command -v gio >/dev/null 2>&1; then
    gio set "$target" metadata::trusted true >/dev/null 2>&1 || true
  fi
}

preserve_and_install_entry "$STANDARD_ENTRY"
for directory in "${SHORTCUT_DIRS[@]}"; do
  preserve_and_install_entry "$directory/Elysia.desktop"
done

cat >"$RECEIPT_ROOT/desktop-install-receipt.json" <<EOF
{"contract":"elysia-desktop-user-install-1.0","operation":"$OPERATION","package_sha256":"$PACKAGE_SHA256","release_id":"$RELEASE_ID","stable_launcher":true,"standard_desktop_entry":true,"user_data_preserved":true,"network_used":false,"raw_paths_exposed":false}
EOF
chmod 0600 "$RECEIPT_ROOT/desktop-install-receipt.json"
MANAGED_ENTRIES="$RECEIPT_ROOT/desktop-managed-entries.txt"
{
  printf '%s\n' "$STANDARD_ENTRY"
  for directory in "${SHORTCUT_DIRS[@]}"; do
    printf '%s\n' "$directory/Elysia.desktop"
  done
} >"$MANAGED_ENTRIES"
chmod 0600 "$MANAGED_ENTRIES"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_ROOT" >/dev/null 2>&1 || true
fi

echo "Elysia Desktop $OPERATION complete. Every generated entry converges on the stable user-local launcher."
