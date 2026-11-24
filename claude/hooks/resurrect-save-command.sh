#!/usr/bin/env bash
# tmux-resurrect save strategy (@resurrect-save-command-strategy in claude-agent.tmux.conf).
# Same as resurrect's "ps" strategy: save the command a pane's shell is running.
# Except: when Claude is the pane's own process (started as `tmux split-window "claude ..."`),
# "ps" saves Claude's first child (an MCP server), so a restore wouldn't resume that pane.
# Prints Claude's own command instead, which @resurrect-processes "~claude" picks up.

PANE_PID="$1"
[ -z "$PANE_PID" ] && exit 0

own="$(ps -o args= -p "$PANE_PID")"
case "$own" in
	claude | claude\ * | */claude | */claude\ *) echo "$own"; exit 0 ;;
esac

ps -ao "ppid,args" |
	sed "s/^ *//" |
	grep "^${PANE_PID} " |
	cut -d' ' -f2-
