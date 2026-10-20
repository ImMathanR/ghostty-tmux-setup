#!/usr/bin/env bash
# Fails when any tracked text file names a personal home directory or user,
# so the repo works the same on any machine and for any user.
set -euo pipefail
cd "$(dirname "$0")/.."

me=$(id -un)
pattern="/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|/root/|$me"
# This script names the patterns it looks for, so skip it. /home/linuxbrew
# is Homebrew's own prefix on Linux, not a person's home.
hits=$(git ls-files -co --exclude-standard -z \
  | grep -zv '^tests/check-paths.sh$' \
  | xargs -0 grep -nIE "$pattern" -- 2>/dev/null \
  | grep -v '/home/linuxbrew' || true)

if [ -n "$hits" ]; then
  echo "FAIL: personal paths or user names found:" >&2
  echo "$hits" >&2
  exit 1
fi
echo "ok: no personal paths"
