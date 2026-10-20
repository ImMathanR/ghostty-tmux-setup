#!/bin/bash
# SessionStart: give each new interactive Claude Code session a random prompt-bar /color.
# There is no setting or hook output for /color, so this types the command into the session's own tmux pane.
# The typing step runs inside the tmux server (run-shell -b) because Claude kills the hook's children when it exits.

if [ "$1" = --type ]; then
  pane=$2 pick=$3
  # Wait for an empty prompt (only the dim placeholder after ❯), so we never mix into what the user is typing.
  for _ in $(seq 1 40); do
    line=$(tmux capture-pane -p -e -t "$pane" 2>/dev/null | grep -m1 '❯')
    rest=${line#*❯}
    rest=${rest#$'\xc2\xa0'}  # the prompt puts a non-breaking space after ❯
    rest=${rest# }
    rest=${rest#$'\e[0m'}
    if [ -n "$line" ] && { [ -z "${rest//[[:space:]]/}" ] || [[ "$rest" == $'\e[2m'* ]]; }; then
      tmux send-keys -t "$pane" -l "/color $pick"
      tmux send-keys -t "$pane" Enter
      exit 0
    fi
    sleep 0.25
  done
  exit 0
fi

[ -n "$TMUX_PANE" ] || exit 0
command -v tmux >/dev/null || exit 0

# Find the claude process that ran this hook; skip headless (-p/--print) runs.
pid=$PPID
args=
while [ -n "$pid" ] && [ "$pid" -gt 1 ]; do
  if [ "$(basename "$(ps -o comm= -p "$pid" 2>/dev/null)")" = claude ]; then
    args=$(ps -o args= -p "$pid" 2>/dev/null)
    break
  fi
  pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
done
case " $args " in "  "|*" -p "*|*" --print "*) exit 0 ;; esac

# Only type into the pane if that claude is the one attached to it (not a background agent that inherited TMUX_PANE).
claude_tty=/dev/$(ps -o tty= -p "$pid" 2>/dev/null | tr -d ' ')
[ "$claude_tty" = "$(tmux display -p -t "$TMUX_PANE" '#{pane_tty}' 2>/dev/null)" ] || exit 0

colors=(red blue green yellow purple orange pink cyan)
pick=${colors[RANDOM % ${#colors[@]}]}
tmux run-shell -b "bash '$0' --type '$TMUX_PANE' '$pick'"
exit 0
