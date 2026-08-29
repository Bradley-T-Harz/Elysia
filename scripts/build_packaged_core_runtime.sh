#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_TAURI_DIR="$ROOT_DIR/apps/elysia-desktop/src-tauri"
PACKAGE_PYTHON="${ELYSIA_PACKAGE_PYTHON:-python3}"

if ! command -v "$PACKAGE_PYTHON" >/dev/null 2>&1; then
  echo "ELYSIA_PACKAGE_PYTHON must name an available Python interpreter." >&2
  exit 2
fi
if ! command -v rustc >/dev/null 2>&1; then
  echo "Rust is required to resolve the Tauri target triple." >&2
  exit 2
fi

TARGET_TRIPLE="${ELYSIA_PACKAGE_TARGET_TRIPLE:-$(rustc -vV | awk '/^host: / { print $2 }')}"
case "$TARGET_TRIPLE" in
  x86_64-unknown-linux-gnu) ;;
  *)
    echo "Pass 10 Linux packaging currently supports x86_64-unknown-linux-gnu only." >&2
    exit 2
    ;;
esac

(
cd "$ROOT_DIR"
"$PACKAGE_PYTHON" - <<'PY'
from importlib.metadata import version
from pathlib import Path
import sys

from app.install.python_lock_service import assert_environment_matches_locks_exact

expected = Path("requirements/build.txt").read_text(encoding="utf-8").strip().split("==", 1)[1]
actual = version("pyinstaller")
if actual != expected:
    raise SystemExit(f"PyInstaller {expected} is required; found {actual}.")
if sys.version_info[:2] != (3, 12):
    raise SystemExit("The packaged Core runtime must be built with Python 3.12.")
assert_environment_matches_locks_exact(
    [
        Path("config/install/locks/core-py312.lock.txt"),
        Path("config/install/locks/build-py312.lock.txt"),
    ],
    allowed_additional={"pip"},
)
PY
)

BUILD_ROOT="$(mktemp -d /tmp/elysia-packaged-core-build.XXXXXXXX)"
DIST_DIR="$BUILD_ROOT/dist"
WORK_DIR="$BUILD_ROOT/work"
SPEC_DIR="$BUILD_ROOT/spec"
BINARY_DIR="$DESKTOP_TAURI_DIR/binaries"
TARGET_BINARY="$BINARY_DIR/elysia-$TARGET_TRIPLE"

mkdir -p "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR" "$BINARY_DIR"

module_flags=()
while IFS= read -r module_path; do
  module="${module_path%.py}"
  module="${module//\//.}"
  module_flags+=(--hidden-import "$module")
done < <(cd "$ROOT_DIR" && find app core -type f -name '*.py' -print | sort)

metadata_flags=()
for distribution in \
  fastapi uvicorn pydantic PyYAML pwdlib cryptography zstandard Pillow numpy defusedxml CairoSVG imageio pytesseract
do
  metadata_flags+=(--copy-metadata "$distribution")
done

hidden_runtime_flags=()
for module in pwdlib cryptography zstandard PIL numpy defusedxml cairosvg imageio pytesseract
do
  hidden_runtime_flags+=(--hidden-import "$module")
done

# PyInstaller's Linux dependency resolver can select the host ldconfig copy of
# libexpat even when the selected Python interpreter's pyexpat extension is
# linked to a different build. Bundle the exact library resolved by pyexpat so
# the release sidecar cannot fail later with an undefined Expat symbol.
PACKAGED_LIBEXPAT="$("$PACKAGE_PYTHON" - <<'PY'
from pathlib import Path
import pyexpat
import subprocess
import sys

probe = Path(getattr(pyexpat, "__file__", "") or sys.executable).resolve()
result = subprocess.run(
    ["ldd", str(probe)],
    check=True,
    capture_output=True,
    text=True,
)
for line in result.stdout.splitlines():
    stripped = line.strip()
    if stripped.startswith("libexpat.so") and "=>" in stripped:
        candidate = Path(stripped.split("=>", 1)[1].split("(", 1)[0].strip())
        if candidate.is_file():
            print(candidate.resolve())
            break
else:
    raise SystemExit("Could not resolve the libexpat used by the selected Python pyexpat module.")
PY
)"

(
  cd "$ROOT_DIR"
  env -u PYTHONPATH \
    PYTHONHASHSEED=0 \
    MPLCONFIGDIR="$BUILD_ROOT/matplotlib" \
    "$PACKAGE_PYTHON" -m PyInstaller \
      --noconfirm \
      --clean \
      --onefile \
      --exclude-module psutil \
      --name elysia \
      --distpath "$DIST_DIR" \
      --workpath "$WORK_DIR" \
      --specpath "$SPEC_DIR" \
      --paths "$ROOT_DIR" \
      --add-data "$ROOT_DIR/config:config" \
      --add-data "$ROOT_DIR/skills:skills" \
      --add-data "$ROOT_DIR/scripts/manage_qdrant.sh:scripts" \
      --add-data "$ROOT_DIR/scripts/manage_searxng.sh:scripts" \
      --add-data "$ROOT_DIR/scripts/manage_neurofabric.sh:scripts" \
      --add-data "$ROOT_DIR/scripts/prove_neurofabric_runtime.py:scripts" \
      --add-data "$ROOT_DIR/packaging/core_runtime_prompts:derived/runtime" \
      --add-binary "$PACKAGED_LIBEXPAT:elysia-native" \
      --runtime-hook "$ROOT_DIR/packaging/pyi_rth_elysia_native.py" \
      "${hidden_runtime_flags[@]}" \
      "${metadata_flags[@]}" \
      "${module_flags[@]}" \
      "$ROOT_DIR/packaging/elysia_cli.py"
)

install -m 0755 "$DIST_DIR/elysia" "$TARGET_BINARY"

"$PACKAGE_PYTHON" "$ROOT_DIR/scripts/verify_packaged_core_routes.py" "$TARGET_BINARY"

"$PACKAGE_PYTHON" - "$TARGET_BINARY" "$ROOT_DIR" "${HOME:-}" <<'PY'
from pathlib import Path
import sys

binary = Path(sys.argv[1]).read_bytes()
for marker in (sys.argv[2], sys.argv[3]):
    if marker and marker.encode() in binary:
        raise SystemExit("Packaged Core runtime contains a private build-path marker.")
PY

echo "Packaged Core runtime prepared for Tauri: $TARGET_BINARY"
