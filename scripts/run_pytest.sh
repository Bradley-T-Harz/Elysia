#!/usr/bin/env bash
set -euo pipefail

TEST_PYTHON="${ELYSIA_TEST_PYTHON:-python}"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$TEST_PYTHON" -m pytest "$@"
