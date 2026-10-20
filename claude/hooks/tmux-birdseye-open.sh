#!/bin/sh
# Shows birdseye (a live, zoomable map of every tmux tab) in its own tmux tab,
# reusing that tab when it's already running. Bound to the ▦ in the status bar.
H="$(cd "$(dirname "$0")" && pwd)"
W=$(tmux list-windows -F '#{window_id} #{@birdseye}' | awk '$2 == 1 { print $1; exit }')
if [ -n "$W" ]; then
  tmux select-window -t "$W"
else
  tmux new-window -n birdseye "python3 '$H/birdseye/tui.py'" \; \
    set -w @birdseye 1 \; set -w automatic-rename off
fi
