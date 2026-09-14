#!/usr/bin/env bash
set -Eeuo pipefail
[[ "${1:---dry-run}" == --apply || "${1:---dry-run}" == --dry-run ]] || { echo 'Usage: uninstall_codev_core_user.sh [--apply|--dry-run]' >&2; exit 2; }
CODEV_USER_HOME="${HOME:?HOME is required}"
CODEV_DATA_BASE="${XDG_DATA_HOME:-$CODEV_USER_HOME/.local/share}"
CODEV_CONFIG_BASE="${XDG_CONFIG_HOME:-$CODEV_USER_HOME/.config}"
[[ "$CODEV_USER_HOME" = /* && "$CODEV_DATA_BASE" = /* && "$CODEV_CONFIG_BASE" = /* ]] || { echo 'Absolute HOME/XDG paths are required.' >&2; exit 2; }
CODEV_CURRENT="$CODEV_DATA_BASE/codev/current"
[[ -L "$CODEV_CURRENT" && -O "$CODEV_CURRENT" && "$(readlink "$CODEV_CURRENT")" =~ ^releases/[a-f0-9]{16}$ ]] || { echo 'No owned user-local Codev installation was found. System packages must be removed with the package manager.' >&2; exit 2; }
echo 'Uninstall user-local Codev Core; preserve recoverable packages, account data, repositories, models and the optional VS Code client.'
[[ "${1:---dry-run}" == --apply ]] || exit 0
# Removing identity immediately makes every canonical operation fail closed.
# Reinstall selects a new link generation, so old actors cannot regain grants.
unlink "$CODEV_CURRENT"
CODEV_LAUNCHER="$CODEV_USER_HOME/.local/bin/codev"
if [[ -f "$CODEV_LAUNCHER" && ! -L "$CODEV_LAUNCHER" ]] && grep -Fq 'codev/current/usr/lib/codev/codev-core' "$CODEV_LAUNCHER"; then rm -- "$CODEV_LAUNCHER"; fi
CODEV_AUTOSTART="$CODEV_CONFIG_BASE/autostart/codev-core.desktop"
if [[ -f "$CODEV_AUTOSTART" && ! -L "$CODEV_AUTOSTART" ]] && grep -Fq 'Name=Codev Core' "$CODEV_AUTOSTART"; then rm -- "$CODEV_AUTOSTART"; fi
echo 'Codev Core uninstalled. Elysia refreshes installation truth automatically. No repository files were changed.'
