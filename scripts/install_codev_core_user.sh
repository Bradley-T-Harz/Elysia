#!/usr/bin/env bash
# Install a distributable Codev Core Debian payload in the current user's XDG
# data tree. No editor, source checkout, Python environment or root is needed.
set -Eeuo pipefail
CODEV_INSTALL_MODE=dry-run
CODEV_DEB=""
while (($#)); do
  case "$1" in
    --apply) CODEV_INSTALL_MODE=apply; shift ;;
    --dry-run) CODEV_INSTALL_MODE=dry-run; shift ;;
    --deb) CODEV_DEB="${2:-}"; shift 2 ;;
    --help|-h) echo 'Usage: install_codev_core_user.sh --deb /absolute/Codev_Core_1.1.0_amd64.deb [--apply]'; exit 0 ;;
    *) echo 'Unsupported installer argument.' >&2; exit 2 ;;
  esac
done
CODEV_USER_HOME="${HOME:?HOME is required}"
CODEV_DATA_BASE="${XDG_DATA_HOME:-$CODEV_USER_HOME/.local/share}"
CODEV_CONFIG_BASE="${XDG_CONFIG_HOME:-$CODEV_USER_HOME/.config}"
[[ "$CODEV_USER_HOME" = /* && "$CODEV_DATA_BASE" = /* && "$CODEV_CONFIG_BASE" = /* ]] || { echo 'Absolute HOME/XDG paths are required.' >&2; exit 2; }
[[ "$CODEV_DEB" = /* && -f "$CODEV_DEB" && ! -L "$CODEV_DEB" ]] || { echo 'Select one absolute non-symlink Debian artifact.' >&2; exit 2; }
[[ $(stat -c %s "$CODEV_DEB") -le 209715200 ]] || { echo 'Codev artifact exceeds the package limit.' >&2; exit 2; }
[[ "$(dpkg-deb -f "$CODEV_DEB" Package)" == codev-core && "$(dpkg-deb -f "$CODEV_DEB" Version)" == 1.1.0 && "$(dpkg-deb -f "$CODEV_DEB" Architecture)" == amd64 ]] || { echo 'Incompatible Codev Core package.' >&2; exit 2; }
[[ $(uname -m) == x86_64 ]] || { echo 'This artifact requires amd64 Linux.' >&2; exit 2; }
CODEV_PACKAGE_DIGEST="$(sha256sum "$CODEV_DEB" | cut -d ' ' -f1)"
echo "Codev Core 1.1.0 package: $CODEV_PACKAGE_DIGEST"
echo 'Install/repair the neutral runtime and login startup. VS Code is optional.'
echo 'No workspace, profile selection, command, network, or website authority is granted.'
if [[ "$CODEV_INSTALL_MODE" != apply ]]; then echo 'Dry run complete.'; exit 0; fi
umask 077
CODEV_ROOT="$CODEV_DATA_BASE/codev"
CODEV_RELEASES="$CODEV_ROOT/releases"
CODEV_RELEASE="$CODEV_RELEASES/${CODEV_PACKAGE_DIGEST:0:16}"
CODEV_LAUNCHER="$CODEV_USER_HOME/.local/bin/codev"
if [[ -e "$CODEV_LAUNCHER" || -L "$CODEV_LAUNCHER" ]]; then
  [[ -f "$CODEV_LAUNCHER" && ! -L "$CODEV_LAUNCHER" && -O "$CODEV_LAUNCHER" ]] && grep -Fq 'codev/current/usr/lib/codev/codev-core' "$CODEV_LAUNCHER" || {
    echo 'An unrelated codev launcher exists; installation was not changed.' >&2; exit 2;
  }
fi
for directory in "$CODEV_ROOT" "$CODEV_RELEASES" "$CODEV_USER_HOME/.local/bin" "$CODEV_CONFIG_BASE/autostart"; do
  [[ ! -L "$directory" ]] || { echo 'Refusing a symlinked installer directory.' >&2; exit 2; }
  mkdir -p "$directory"
  [[ -O "$directory" ]] || { echo 'Installer directory is not owned by the current user.' >&2; exit 2; }
done
chmod 0700 "$CODEV_ROOT" "$CODEV_RELEASES"
CODEV_STAGE="$(mktemp -d "$CODEV_RELEASES/.staging.XXXXXXXX")"
trap 'if [[ -n "${CODEV_STAGE:-}" && -d "$CODEV_STAGE" ]]; then rm -rf -- "$CODEV_STAGE"; fi' EXIT
# Pin exact approved bytes in the private staging directory before parsing.
cp --reflink=auto -- "$CODEV_DEB" "$CODEV_STAGE/package.deb"
[[ "$(sha256sum "$CODEV_STAGE/package.deb" | cut -d ' ' -f1)" == "$CODEV_PACKAGE_DIGEST" ]] || { echo 'The selected package changed while it was copied.' >&2; exit 2; }
# Reject links BEFORE extraction, including links later overwritten by regular
# members. Bound declared expanded size and count; GNU tar also rejects .. paths.
timeout 45 dpkg-deb --fsys-tarfile "$CODEV_STAGE/package.deb" | tar --numeric-owner -tvf - | awk '
  { count++; size += $3; if ($1 !~ /^[-d]/ || count > 500 || size > 314572800) bad = 1 }
  END { exit bad ? 1 : 0 }
' || { echo 'Unsafe or oversized Codev package archive.' >&2; exit 2; }
mkdir "$CODEV_STAGE/payload"
(ulimit -f 614400; timeout 45 dpkg-deb -x "$CODEV_STAGE/package.deb" "$CODEV_STAGE/payload")
rm -- "$CODEV_STAGE/package.deb"
CODEV_UNPACKED="$CODEV_STAGE/payload"
if find "$CODEV_STAGE" ! -type f ! -type d -print -quit | read -r _; then echo 'Package contains a link or special file.' >&2; exit 2; fi
CODEV_PAYLOAD="$CODEV_UNPACKED/usr/lib/codev"
[[ -x "$CODEV_PAYLOAD/codev-core" && -f "$CODEV_PAYLOAD/runtime.json" ]] || { echo 'The package lacks neutral Codev Core payload.' >&2; exit 2; }
# Validate the manifest and compiled payload through the packaged resolver,
# before any launcher/current release is selected. The CLI never runs scripts
# from a workspace or changes account governance.
env -u PYTHONPATH -u LD_LIBRARY_PATH -u CONDA_PREFIX -u CONDA_DEFAULT_ENV "$CODEV_PAYLOAD/codev-core" codev-package-check --root "$CODEV_UNPACKED"
if [[ -e "$CODEV_RELEASE" || -L "$CODEV_RELEASE" ]]; then
  [[ -d "$CODEV_RELEASE" && ! -L "$CODEV_RELEASE" ]] || { echo 'Unsafe existing release.' >&2; exit 2; }
  # Equal bytes do not imply a healthy installation: lost execute bits or
  # group-writable policy files must also be repaired. Compare metadata without
  # following links; retain a damaged release before selecting verified files.
  if diff -qr --no-dereference "$CODEV_UNPACKED" "$CODEV_RELEASE" >/dev/null &&
     cmp -s <(cd "$CODEV_UNPACKED" && find . -printf '%P\t%y\t%m\t%U\t%G\t%n\0' | LC_ALL=C sort -z) \
            <(cd "$CODEV_RELEASE" && find . -printf '%P\t%y\t%m\t%U\t%G\t%n\0' | LC_ALL=C sort -z); then
    rm -rf -- "$CODEV_STAGE"
  else
    mkdir -p "$CODEV_ROOT/recoverable"
    mv "$CODEV_RELEASE" "$CODEV_ROOT/recoverable/$(basename "$CODEV_RELEASE")-$(date -u +%s)-$$"
    mv "$CODEV_UNPACKED" "$CODEV_RELEASE"
  fi
else
  mv "$CODEV_UNPACKED" "$CODEV_RELEASE"
fi
rmdir "$CODEV_STAGE" 2>/dev/null || true
CODEV_STAGE=""
CODEV_LINK="$CODEV_ROOT/.current-$$"
ln -s "releases/$(basename "$CODEV_RELEASE")" "$CODEV_LINK"
mv -Tf "$CODEV_LINK" "$CODEV_ROOT/current"
cat >"$CODEV_ROOT/.launcher-$$" <<'EOF'
#!/bin/sh
set -eu
CODEV_DATA_BASE="${XDG_DATA_HOME:-${HOME:?HOME is required}/.local/share}"
exec env -u PYTHONPATH -u LD_LIBRARY_PATH -u CONDA_PREFIX -u CONDA_DEFAULT_ENV "$CODEV_DATA_BASE/codev/current/usr/lib/codev/codev-core" "$@"
EOF
chmod 0700 "$CODEV_ROOT/.launcher-$$"
mv -f "$CODEV_ROOT/.launcher-$$" "$CODEV_LAUNCHER"
# Use a fixed shell-free freedesktop command. The installed Core resolves XDG
# itself; the desktop entry never embeds the user's name or home path.
cat >"$CODEV_CONFIG_BASE/autostart/codev-core.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Codev Core
Comment=Start the private installed Codev runtime without workspace grants.
Exec=codev runtime ensure
TryExec=codev
NoDisplay=true
Terminal=false
EOF
chmod 0600 "$CODEV_CONFIG_BASE/autostart/codev-core.desktop"
# Login PATH can omit ~/.local/bin. The matching XDG autostart helper uses the
# installed user launcher through its absolute, safely quoted Desktop Exec.
env -u PYTHONPATH -u LD_LIBRARY_PATH "$CODEV_LAUNCHER" codev-user-autostart
"$CODEV_LAUNCHER" runtime ensure
"$CODEV_LAUNCHER" codev-status
echo 'Codev Core installed. Open Elysia; choose a workspace only when needed.'
echo 'To install the optional VS Code client: codev codev-adapter --editor code [--profile PROFILE]'
