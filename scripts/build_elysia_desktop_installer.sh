#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

npm --prefix "$ROOT_DIR/apps/elysia-desktop" run typecheck
npm --prefix "$ROOT_DIR/apps/elysia-desktop" run build
npm --prefix "$ROOT_DIR/apps/elysia-desktop" run tauri:build:linux
