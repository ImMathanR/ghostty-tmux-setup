#!/bin/sh
# tmux-resurrect @resurrect-hook-post-restore-all: show every pane after a restore.
# resurrect re-zooms windows that were zoomed when saved, which hides their other panes.
tmux list-windows -a -F '#{session_name}:#{window_index} #{window_zoomed_flag}' |
	awk '$2 == 1 { print $1 }' |
	while read -r w; do tmux resize-pane -Z -t "$w"; done
