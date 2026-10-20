#!/usr/bin/env bash
# Runs every check: personal paths, unit tests, then the end-to-end smoke test.
set -euo pipefail
cd "$(dirname "$0")/.."
tests/check-paths.sh
python3 -m pytest -q -p no:cacheprovider claude
tests/smoke.sh
