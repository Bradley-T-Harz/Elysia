#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPIMAGE="${ELYSIA_APPIMAGE_PATH:-$ROOT_DIR/apps/elysia-desktop/src-tauri/target/release/bundle/appimage/Elysia_1.0.0_amd64.AppImage}"
PLUGIN="${TAURI_APPIMAGE_PLUGIN:-${HOME:-}/.cache/tauri/linuxdeploy-plugin-appimage.AppImage}"

if [[ ! -x "$APPIMAGE" ]]; then
  echo "The built Elysia AppImage is missing or not executable." >&2
  exit 2
fi
if [[ ! -x "$PLUGIN" ]]; then
  echo "The cached Tauri AppImage packaging plugin is unavailable." >&2
  exit 2
fi
if [[ ! "${SOURCE_DATE_EPOCH:-}" =~ ^[0-9]+$ ]]; then
  echo "A non-negative SOURCE_DATE_EPOCH is required for AppImage normalization." >&2
  exit 2
fi

WORK_ROOT="$(mktemp -d /tmp/elysia-appimage-sanitize.XXXXXXXX)"
EXTRACT_ROOT="$WORK_ROOT/extract"
VERIFY_ROOT="$WORK_ROOT/verify"
PLUGIN_ROOT="$WORK_ROOT/plugin"
OUTPUT="$WORK_ROOT/$(basename "$APPIMAGE")"
RUNTIME_FILE="${ELYSIA_APPIMAGE_RUNTIME_FILE:-$WORK_ROOT/runtime-x86_64}"
SORT_FILE="$WORK_ROOT/mksquashfs.sort"
mkdir -p "$EXTRACT_ROOT" "$VERIFY_ROOT" "$PLUGIN_ROOT"
trap 'rm -rf -- "$WORK_ROOT"' EXIT

python3 "$ROOT_DIR/scripts/package_build_tools.py" verify-tauri-cache \
  --cache "$(dirname "$PLUGIN")"
python3 "$ROOT_DIR/scripts/package_build_tools.py" prepare-runtime \
  --output "$RUNTIME_FILE"
(
  cd "$PLUGIN_ROOT"
  "$PLUGIN" --appimage-extract >/dev/null
)
python3 "$ROOT_DIR/scripts/package_build_tools.py" verify-appimagetool \
  --extracted-plugin "$PLUGIN_ROOT/squashfs-root"

(
  cd "$EXTRACT_ROOT"
  "$APPIMAGE" --appimage-extract >/dev/null
)

HOOK="$EXTRACT_ROOT/squashfs-root/apprun-hooks/linuxdeploy-plugin-gtk.sh"
python3 "$ROOT_DIR/scripts/sanitize_appimage_hook.py" "$HOOK"
python3 "$ROOT_DIR/scripts/sanitize_appimage_root.py" "$EXTRACT_ROOT/squashfs-root"
python3 "$ROOT_DIR/scripts/normalize_appimage_metadata.py" \
  "$EXTRACT_ROOT/squashfs-root" "$SOURCE_DATE_EPOCH"
python3 "$ROOT_DIR/scripts/write_appimage_sort_file.py" \
  "$EXTRACT_ROOT/squashfs-root" "$SORT_FILE"
python3 - "$HOOK" "$ROOT_DIR" "${HOME:-}" <<'PY'
from pathlib import Path
import sys

hook = Path(sys.argv[1])
# HOOK is <AppDir>/apprun-hooks/linuxdeploy-plugin-gtk.sh.
root = Path(sys.argv[1]).parents[1]

markers = tuple(
    marker.encode()
    for marker in (sys.argv[2], sys.argv[3])
    if marker
)
for path in root.rglob("*"):
    if path.is_symlink():
        target = path.readlink().as_posix().encode()
        if any(marker in target for marker in markers):
            raise SystemExit("AppImage symlink contains a private build-path marker.")
        continue
    if path.is_file() and any(marker in path.read_bytes() for marker in markers):
        raise SystemExit("AppImage payload contains a private build-path marker.")
PY

ARCH=x86_64 \
  "$PLUGIN_ROOT/squashfs-root/usr/bin/appimagetool" \
  --runtime-file "$RUNTIME_FILE" \
  --mksquashfs-opt=-sort \
  --mksquashfs-opt="$SORT_FILE" \
  --mksquashfs-opt=-no-xattrs \
  "$EXTRACT_ROOT/squashfs-root" -v "$OUTPUT"
install -m 0755 "$OUTPUT" "$APPIMAGE"

(
  cd "$VERIFY_ROOT"
  "$APPIMAGE" --appimage-extract >/dev/null
)
python3 - "$VERIFY_ROOT/squashfs-root" "$ROOT_DIR" "${HOME:-}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
dir_icon = root / ".DirIcon"
if not dir_icon.is_symlink() or dir_icon.readlink().as_posix() != "elysia-desktop.png":
    raise SystemExit("Sanitized AppImage does not use the canonical relative icon link.")
named_icon = root / "elysia-desktop.png"
expected_icon = "usr/share/icons/hicolor/256x256@2/apps/elysia-desktop.png"
if not named_icon.is_symlink() or named_icon.readlink().as_posix() != expected_icon:
    raise SystemExit("Sanitized AppImage does not use the canonical high-resolution icon target.")
native_notices = root / "usr/lib/Elysia/THIRD_PARTY_NOTICES.native.txt"
if not native_notices.is_file() or native_notices.stat().st_size <= 1_000_000:
    raise SystemExit("Sanitized AppImage is missing its full native-library notice payload.")
markers = tuple(
    marker.encode()
    for marker in (sys.argv[2], sys.argv[3])
    if marker
)
for path in root.rglob("*"):
    if path.is_symlink():
        target = path.readlink().as_posix().encode()
        if any(marker in target for marker in markers):
            raise SystemExit("Sanitized AppImage symlink still contains a private build-path marker.")
        continue
    if path.is_file() and any(marker in path.read_bytes() for marker in markers):
        raise SystemExit("Sanitized AppImage still contains a private build-path marker.")
PY

echo "Sanitized AppImage build-path audit passed: $APPIMAGE"
