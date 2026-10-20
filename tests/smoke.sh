#!/usr/bin/env bash
# End-to-end check in a throwaway HOME: installs with --skip-deps, then drives
# a real tmux server (sandboxed through TMUX_TMPDIR, so no running tmux is
# touched) the way Ghostty and Claude Code would.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
H="$(mktemp -d "${TMPDIR:-/tmp}/ghostty-tmux-smoke.XXXXXX")"
# Socket paths are capped at ~104 bytes on macOS, and $TMPDIR is long there.
S="$(mktemp -d /tmp/gts.XXXXXX)"
# Keep tools the real install put in ~/.local/bin (lazygit on Linux).
export PATH="$HOME/.local/bin:$PATH"
export HOME="$H" TMUX_TMPDIR="$S" XDG_CONFIG_HOME="$H/.config"
unset TMUX TMUX_PANE
cleanup() { tmux kill-server 2>/dev/null || true; rm -rf "$H" "$S"; }
trap cleanup EXIT

FAILS=0
pass() { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; FAILS=$((FAILS + 1)); }
expect() { local label="$1"; shift; if "$@"; then pass "$label"; else fail "$label"; fi; }
wait_for() {  # wait_for <seconds> <command...>
  local n=$(( $1 * 10 )); shift
  while [ $n -gt 0 ]; do "$@" && return 0; sleep 0.1; n=$((n - 1)); done
  return 1
}

echo "==> install into $H"
"$REPO/install.sh" --skip-deps >"$H/install.log" 2>&1 || { cat "$H/install.log"; exit 1; }
pass "install.sh --skip-deps"
"$REPO/install.sh" --skip-deps >"$H/install2.log" 2>&1 || { cat "$H/install2.log"; exit 1; }
expect "second run is a no-op (nothing moved aside)" bash -c "! grep -q 'moved aside' '$H/install2.log'"
expect "settings.json hooks not duplicated" python3 - "$H/.claude/settings.json" <<'PY'
import json, sys
h = json.load(open(sys.argv[1]))["hooks"]
raise SystemExit(sum(len(v) for v in h.values()) != 12)
PY

# A painter started by the check could still hold its lock when the first
# real hook runs, which then skips starting one. The painter makes the lock.
expect "installer's tmux check started no tab painter" test ! -e "$HOME/.claude/hooks/.tmux-agent-anim.lock"

echo "==> Ghostty resolves the installed config"
GB="$(command -v ghostty || echo /Applications/Ghostty.app/Contents/MacOS/ghostty)"
if [ -x "$GB" ]; then
  cfg="$("$GB" +show-config 2>&1)"
  # The first custom-shader is ours; Ghostty resolves it next to the real file.
  shader="$(sed -n 's/^custom-shader = //p' <<<"$cfg" | head -1)"
  expect "custom-shader resolves to an existing file (${shader/#$REPO/<repo>})" test -f "$shader"
  expect "ide-keys include is loaded (Cmd+O binding)" grep -q '^keybind = super+o=text:' <<<"$cfg"
  # On macOS Ghostty reads Application Support from the real home, not $HOME,
  # so a config there outside this sandbox wins. install.sh moves it aside.
  host_cfg="$(eval echo "~$(id -un)")/Library/Application Support/com.mitchellh.ghostty/config"
  if [ -e "$host_cfg" ]; then
    echo "  - command check skipped: this machine's own $host_cfg overrides the sandbox"
  else
    expect "command launches ~/.local/bin/ghostty-tmux" grep -q '^command = shell:~/.local/bin/ghostty-tmux$' <<<"$cfg"
  fi
else
  echo "  - Ghostty not installed, skipped"
fi

echo "==> tmux with plugins"
tmux new-session -d -s smoke -x 200 -y 50
expect "prefix is C-a" test "$(tmux show -gv prefix)" = C-a
expect "tmux-resurrect loaded (prefix C-s saves)" wait_for 10 bash -c "tmux list-keys -T prefix C-s 2>/dev/null | grep -q resurrect"
expect "tmux-continuum loaded" bash -c "tmux show -gv status-right | grep -q continuum_save"
expect "agent tab formats wrapped" bash -c "tmux show -gv window-status-format | grep -q @agent_fmt"
expect "status-right has the scoreboard and birdseye button" bash -c "tmux show -gv status-right | grep -q '@agent_score' && tmux show -gv status-right | grep -q birdseye"

echo "==> every key Ghostty sends through the tmux prefix is bound"
keys="$(python3 - "$REPO/ghostty/config" <<'PY'
import re, sys
arrows = {"A": "Up", "B": "Down", "C": "Right", "D": "Left"}
for line in open(sys.argv[1]):
    m = re.match(r"keybind = [^=]+=text:\\x01(.*)", line.strip())
    if not m:
        continue
    t = m.group(1).encode().decode("unicode_escape")
    if t.startswith("\x1b[") and len(t) > 2:
        print(arrows[t[2]])
    elif ord(t[0]) < 32:
        print("C-" + chr(ord(t[0]) + 96))
    else:
        print(t[0])
PY
)"
missing=
for k in $keys; do tmux list-keys -T prefix "$k" >/dev/null 2>&1 || missing="$missing $k"; done
expect "$(wc -w <<<"$keys" | tr -d ' ') prefix keys bound${missing:+ (missing:$missing)}" test -z "$missing"

echo "==> Claude Code hook events paint the tab"
pane="$(tmux display -p -t smoke '#{pane_id}')"
hook() { printf '%s' "$2" | TMUX_PANE="$pane" bash "$HOME/.claude/hooks/tmux-agent-state.sh" "$1"; }
hook working '{"hook_event_name":"UserPromptSubmit","session_id":"abc-123","cwd":"/tmp"}'
expect "UserPromptSubmit → @agent=working" test "$(tmux show -wv -t "$pane" @agent)" = working
expect "painter started and animates the tab" wait_for 5 bash -c "[ -n \"\$(tmux show -wqv -t $pane @agent_fmt)\" ]"
expect "conversation recorded for crash restore" grep -q abc-123 "$HOME/.claude/hooks/.tmux-claude-sessions.json"
hook ask '{"hook_event_name":"Notification","notification_type":"permission_prompt"}'
expect "permission prompt → @agent=ask" test "$(tmux show -wv -t "$pane" @agent)" = ask
hook "done" '{"hook_event_name":"Stop"}'
expect "Stop (tab not focused) → @agent=done" test "$(tmux show -wv -t "$pane" @agent)" = "done"
hook failed '{"hook_event_name":"StopFailure"}'
expect "StopFailure → @agent=failed" test "$(tmux show -wv -t "$pane" @agent)" = failed
hook off '{"hook_event_name":"SessionEnd"}'
expect "SessionEnd clears the badge" test -z "$(tmux show -wqv -t "$pane" @agent)"

echo "==> launcher attaches a client, cat sticker renders"
tmux kill-server 2>/dev/null || true
# script gives the client a terminal; the sleep keeps its stdin open.
# tmux won't attach without a capable TERM (Ghostty sets one; containers don't).
case "${TERM:-dumb}" in dumb|unknown) export TERM=xterm-256color ;; esac
if script --version 2>/dev/null | grep -q util-linux; then   # Linux
  sleep 60 | script -q -c "$HOME/.local/bin/ghostty-tmux launched" /dev/null >/dev/null 2>&1 &
else                                                          # macOS/BSD
  sleep 60 | script -q /dev/null "$HOME/.local/bin/ghostty-tmux" launched >/dev/null 2>&1 &
fi
expect "ghostty-tmux created and attached session 'launched'" \
  wait_for 10 bash -c "tmux list-clients -t launched -F x 2>/dev/null | grep -q x"
expect "launcher reattaches instead of creating a duplicate" bash -c "[ \$(tmux ls | wc -l) -eq 1 ]"
tmux send-keys -t launched "python3 \$HOME/.claude/hooks/tmux-agent-sticker.py done 1:smoke 0.5; echo sticker-exit=\$?" Enter
expect "sticker drew its frames and exited cleanly" \
  wait_for 20 bash -c "tmux capture-pane -p -t launched | grep -q 'sticker-exit=0' && ls '$HOME/.claude/hooks/.sticker-cache'/done-0.png >/dev/null 2>&1"

echo
if [ "$FAILS" -gt 0 ]; then echo "FAILED: $FAILS check(s)"; exit 1; fi
echo "all smoke checks passed"
