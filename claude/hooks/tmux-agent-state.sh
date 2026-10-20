#!/bin/sh
# Mirrors Claude Code's state onto its tmux window as @agent, which the
# status bar formats in ~/.claude/hooks/claude-agent.tmux.conf render.
#   working  Claude is busy
#   ask      Claude is blocked on you (permission, question, plan approval)
#   done     turn finished while you were looking elsewhere
#   failed   turn ended on an API error (StopFailure); stays until next prompt
#   (unset)  nothing to report
[ -n "${TMUX_PANE:-}" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

state="${1:-}"
input=$(cat)
# one jq call for all fields (each program launch is scanned by endpoint security)
eval "$(printf '%s' "$input" | jq -r '@sh "event=\(.hook_event_name // "") agent=\(.agent_id // "") ntype=\(.notification_type // "") tool=\(.tool_name // "")"' 2>/dev/null)"

# Subagents never drive the badge. Their start/stop is kept as one file per
# subagent under .subagents/<pane>/, which the birdseye view counts; a file per
# subagent means parallel hooks can't lose each other's updates.
subs="$(dirname "$0")/.subagents/$TMUX_PANE"
# The count also goes on the pane as @pane_agent_subs for Archipelago's kittens.
count_subs() { tmux set -p -t "$TMUX_PANE" @pane_agent_subs "$(ls "$subs" 2>/dev/null | wc -l | tr -d ' ')"; }
case "$event" in
  SubagentStart) mkdir -p "$subs" && touch "$subs/$agent"; count_subs; exit 0 ;;
  SubagentStop) rm -f "$subs/$agent"; count_subs; exit 0 ;;
  SessionStart|SessionEnd) rm -rf "$subs"; tmux set -pu -t "$TMUX_PANE" @pane_agent_subs ;;
esac
[ -n "$agent" ] && exit 0

case "$event" in
  SessionStart|UserPromptSubmit)
    # remember this pane's conversation so a crash restore can reopen it
    printf '%s' "$input" | python3 "$(dirname "$0")/claude_sessions.py" record 2>/dev/null ;;
esac

case "$event" in
  Notification)
    case "$ntype" in
      permission_prompt|elicitation_dialog) state=ask ;;
      *) exit 0 ;;
    esac ;;
  PreToolUse)
    case "$tool" in
      AskUserQuestion|ExitPlanMode) state=ask ;;
    esac ;;
esac

# A failure stays until real progress (your next prompt, the turn ending, a new
# question). Hooks run in parallel, so a tool hook from the interrupted turn can
# land just after StopFailure; it must not paint the tab "working" again.
if [ "$state" = working ]; then
  case "$event" in
    PreToolUse|PostToolUse|PostToolUseFailure)
      [ "$(tmux show -wqv -t "$TMUX_PANE" @agent)" = failed ] && exit 0 ;;
  esac
fi

if [ "$state" = done ]; then
  # Skip the badge when this window is on screen in a focused terminal.
  set -- $(tmux display -p -t "$TMUX_PANE" '#{window_active} #{session_name}')
  if [ "$1" = 1 ] && tmux list-clients -t "$2" -F '#{client_flags}' 2>/dev/null | grep -q focused; then
    state=off
  fi
fi

# The window copies drive the tab badge. The pane copies are per Claude, for
# Archipelago; they have their own names because a pane option would shadow the
# window one in the tab formats. @pane_agent_tool is the running tool, or empty.
case "$event" in
  PreToolUse) ptool=$tool ;;
  *) ptool= ;;
esac
if [ "$state" = off ]; then
  tmux set -wu -t "$TMUX_PANE" @agent \; set -pu -t "$TMUX_PANE" @pane_agent \; set -pu -t "$TMUX_PANE" @pane_agent_tool
else
  # @agent_at lets the painter tell a fresh event (sticker-worthy) from old state
  tmux set -w -t "$TMUX_PANE" @agent_at "$(date +%s)" \; set -w -t "$TMUX_PANE" @agent "$state" \
    \; set -p -t "$TMUX_PANE" @pane_agent "$state" \; set -p -t "$TMUX_PANE" @pane_agent_tool "$ptool"
fi
# Animator holds a lock, so extra launches exit immediately. It also runs on
# "off" so the tab eases back to plain instead of snapping.
# Start the painter only when it isn't running (it records its pid in the lock).
lock="$(dirname "$0")/.tmux-agent-anim.lock"
kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null ||
  nohup python3 "$(dirname "$0")/tmux-agent-anim.py" </dev/null >/dev/null 2>&1 &
exit 0
