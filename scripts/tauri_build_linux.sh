#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$ROOT_DIR/apps/elysia-desktop"
TAURI_BUNDLES="${ELYSIA_TAURI_BUNDLES:-deb,appimage}"
APPSTREAM_SHIM_DIR="$ROOT_DIR/scripts/packaging_bin"

case "$TAURI_BUNDLES" in
  deb|appimage|deb,appimage|appimage,deb) ;;
  *)
    echo "Unsupported ELYSIA_TAURI_BUNDLES value. Use deb, appimage, or deb,appimage." >&2
    exit 2
    ;;
esac

if [[ -z "${HOME:-}" || "$HOME" != /* ]]; then
  echo "A valid absolute user home is required for sanitized package path remapping." >&2
  exit 2
fi

if [[ -n "${RUSTFLAGS:-}" || -n "${CARGO_ENCODED_RUSTFLAGS:-}" ]]; then
  echo "Custom Rust flags are not accepted by the public package wrapper." >&2
  exit 2
fi

# Every supported Linux package invocation must bind current Python source to
# the Tauri sidecar. Reusing a previously built Core can produce green desktop
# bytes that silently omit the latest backend repair.
"$ROOT_DIR/scripts/build_packaged_core_runtime.sh"

# Cargo and third-party crates can embed compiler source paths in panic metadata.
# Use Cargo's unit-separator encoding so homes containing spaces remain one flag.
export CARGO_ENCODED_RUSTFLAGS="--remap-path-prefix=${HOME}=/build/user"

# Tauri emits a legacy Elysia.appdata.xml alias next to the canonical
# reverse-DNS metainfo filename. appimagetool rejects that duplicate filename
# even when both files are byte-identical, and its default validator also
# makes an otherwise deterministic local build depend on network reachability.
# The packaging-only shim verifies the alias, removes it only for validation,
# and preserves every other AppStream error.
if [[ ",$TAURI_BUNDLES," == *,appimage,* ]]; then
  if [[ ! -x "$APPSTREAM_SHIM_DIR/appstreamcli" ]]; then
    echo "The packaging AppStream validator shim is missing or not executable." >&2
    exit 2
  fi
  export PATH="$APPSTREAM_SHIM_DIR:$PATH"
  python3 "$ROOT_DIR/scripts/package_build_tools.py" verify-tauri-cache \
    --cache "$HOME/.cache/tauri"
  APPIMAGE_RUNTIME_FILE="$HOME/.cache/tauri/runtime-x86_64"
  python3 "$ROOT_DIR/scripts/package_build_tools.py" prepare-runtime \
    --output "$APPIMAGE_RUNTIME_FILE"
  # New appimagetool releases acquire the type-2 runtime separately. Bind the
  # exact verified runtime before linuxdeploy starts so package construction is
  # offline-reproducible and cannot silently follow a mutable network channel.
  export LDAI_RUNTIME_FILE="$APPIMAGE_RUNTIME_FILE"
  export ELYSIA_APPIMAGE_RUNTIME_FILE="$APPIMAGE_RUNTIME_FILE"
fi

npm --prefix "$DESKTOP_DIR" run tauri -- build --bundles "$TAURI_BUNDLES"
python3 "$ROOT_DIR/scripts/validate_desktop_csp_assets.py" \
  --config "$DESKTOP_DIR/src-tauri/tauri.conf.json" \
  --dist "$DESKTOP_DIR/dist"

case ",$TAURI_BUNDLES," in
  *,deb,*)
    python3 "$ROOT_DIR/scripts/normalize_deb_bundle.py" \
      "$DESKTOP_DIR/src-tauri/target/release/bundle/deb/Elysia_1.0.0_amd64.deb"
    ;;
esac

case ",$TAURI_BUNDLES," in
  *,appimage,*)
    NATIVE_NOTICE_CHECK="$(mktemp /tmp/elysia-native-notices.XXXXXXXX)"
    trap 'rm -f -- "$NATIVE_NOTICE_CHECK"' EXIT
    python3 "$ROOT_DIR/scripts/generate_appimage_native_notices.py" \
      --appdir "$DESKTOP_DIR/src-tauri/target/release/bundle/appimage/Elysia.AppDir" \
      --output "$NATIVE_NOTICE_CHECK"
    if ! cmp -s -- "$NATIVE_NOTICE_CHECK" "$DESKTOP_DIR/THIRD_PARTY_NOTICES.native.txt"; then
      echo "The AppImage native notice payload is stale. Regenerate it and rebuild so exact package contents and notices remain bound." >&2
      exit 2
    fi
    rm -f -- "$NATIVE_NOTICE_CHECK"
    trap - EXIT
    "$ROOT_DIR/scripts/sanitize_appimage_bundle.sh"
    ;;
esac

# A deb and AppImage built as one package family must contain the same packaged
# Core program. linuxdeploy legitimately adds an AppDir-relative RUNPATH to the
# ELF wrapper, so whole-file identity would reject the required loader fix.
# Instead, bind the stable GNU build identity and the exact complete PyInstaller
# CArchive payload, which contains every packaged Python module and resource.
if [[ ",$TAURI_BUNDLES," == *,deb,* && ",$TAURI_BUNDLES," == *,appimage,* ]]; then
  FAMILY_VERIFY_ROOT="$(mktemp -d /tmp/elysia-package-family.XXXXXXXX)"
  trap 'rm -rf -- "$FAMILY_VERIFY_ROOT"' EXIT
  DEB_ARTIFACT="$DESKTOP_DIR/src-tauri/target/release/bundle/deb/Elysia_1.0.0_amd64.deb"
  APPIMAGE_ARTIFACT="$DESKTOP_DIR/src-tauri/target/release/bundle/appimage/Elysia_1.0.0_amd64.AppImage"
  dpkg-deb -x "$DEB_ARTIFACT" "$FAMILY_VERIFY_ROOT/deb"
  (
    cd "$FAMILY_VERIFY_ROOT"
    "$APPIMAGE_ARTIFACT" --appimage-extract >/dev/null
  )
  DEB_CORE="$FAMILY_VERIFY_ROOT/deb/usr/bin/elysia"
  APPIMAGE_CORE="$FAMILY_VERIFY_ROOT/squashfs-root/usr/bin/elysia"
  objcopy --dump-section .note.gnu.build-id="$FAMILY_VERIFY_ROOT/deb.build-id" "$DEB_CORE" /dev/null
  objcopy --dump-section .note.gnu.build-id="$FAMILY_VERIFY_ROOT/appimage.build-id" "$APPIMAGE_CORE" /dev/null
  if ! cmp -s "$FAMILY_VERIFY_ROOT/deb.build-id" "$FAMILY_VERIFY_ROOT/appimage.build-id"; then
    echo "The deb and AppImage packaged Core build identities do not match." >&2
    exit 2
  fi
  if ! readelf -d "$APPIMAGE_CORE" | grep -Fq 'Library runpath: [$ORIGIN/../lib]'; then
    echo "The AppImage packaged Core is missing its required relative library RUNPATH." >&2
    exit 2
  fi
  python3 - "$DEB_CORE" "$APPIMAGE_CORE" <<'PY'
from pathlib import Path
import struct
import sys

COOKIE_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE_SIZE = 88


def carchive(path: str) -> bytes:
    payload = Path(path).read_bytes()
    cookie_start = payload.rfind(COOKIE_MAGIC)
    if cookie_start < 0 or cookie_start + COOKIE_SIZE > len(payload):
        raise SystemExit("A packaged Core is missing its PyInstaller archive cookie.")
    package_length = struct.unpack("!I", payload[cookie_start + 8:cookie_start + 12])[0]
    archive_start = cookie_start + COOKIE_SIZE - package_length
    if archive_start < 0:
        raise SystemExit("A packaged Core has an invalid PyInstaller archive length.")
    return payload[archive_start:cookie_start + COOKIE_SIZE]


if carchive(sys.argv[1]) != carchive(sys.argv[2]):
    raise SystemExit("The deb and AppImage do not contain the same packaged Elysia Core archive.")
PY
  echo "Linux package-family Core build/archive identity audit passed."
fi
