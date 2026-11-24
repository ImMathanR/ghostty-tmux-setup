#!/bin/bash
# Claude Code state -> Rex, through the Program Status Protocol (OSC 7501):
# https://www.superlogical.com/rex/docs/build/program-status
# Rex then shows a spinner on unfocused tabs, a symbol when Claude waits on you,
# and markers in the session picker. Called by tmux-agent-state.sh when the
# session runs in Rex without tmux, with the same argument it was given:
#   working | ask | done | failed | off | sub
# Pure bash on the common path: every program launch waits on endpoint security.
[ -n "${REX_SESSION:-}" ] || exit 0
arg="${1:-}"
input=$(cat)
input=${input//\": \"/\":\"}   # tolerate "key": "value" spacing

field() {  # field NAME -> $REPLY (string fields only)
  local k="\"$1\":\"" r=${input#*\"$1\":\"}
  REPLY=
  [ "$r" = "$input" ] && return
  REPLY=${r%%\"*}
}

b64() {  # ASCII text -> $REPLY, standard base64
  local s=$1 out= i n=${#1} a b c t chars=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/
  for ((i = 0; i < n; i += 3)); do
    printf -v a '%d' "'${s:i:1}"
    b=0; c=0
    ((i + 1 < n)) && printf -v b '%d' "'${s:i+1:1}"
    ((i + 2 < n)) && printf -v c '%d' "'${s:i+2:1}"
    t=$((a << 16 | b << 8 | c))
    out+=${chars:t>>18&63:1}${chars:t>>12&63:1}
    ((i + 1 < n)) && out+=${chars:t>>6&63:1} || out+==
    ((i + 2 < n)) && out+=${chars:t&63:1} || out+==
  done
  REPLY=$out
}

field hook_event_name; event=$REPLY
field agent_id; agent=$REPLY
field tool_name; tool=$REPLY
field notification_type; ntype=$REPLY
[ -n "$agent" ] && exit 0          # subagents never drive the tab
[ "$arg" = sub ] && exit 0

app=claude-code
body=
case "$event:$arg" in
  SessionEnd:*)       body="state=clear" ;;
  SessionStart:*)     body="state=idle:app=$app" ;;
  Notification:*)
    case "$ntype" in
      permission_prompt)  b64 "Claude needs your permission"; body="state=blocked:kind=permission:app=$app:msg=$REPLY" ;;
      elicitation_dialog) b64 "Claude has a question"; body="state=blocked:kind=question:app=$app:msg=$REPLY" ;;
      *) exit 0 ;;
    esac ;;
  PermissionRequest:*) b64 "Allow ${tool:-a tool}?"; body="state=blocked:kind=permission:app=$app:msg=$REPLY" ;;
  PreToolUse:*)
    case "$tool" in
      AskUserQuestion|ExitPlanMode) b64 "Claude has a question"; body="state=blocked:kind=question:app=$app:msg=$REPLY" ;;
      *) b64 "$tool"; body="state=working:app=$app:msg=$REPLY" ;;
    esac ;;
  PostToolUse:*|PostToolUseFailure:*) b64 "$tool"; body="state=working:app=$app:msg=$REPLY" ;;
  UserPromptSubmit:*) body="state=working:app=$app" ;;
  Stop:*)             b64 "Claude finished"; body="state=done:app=$app:msg=$REPLY" ;;
  StopFailure:*)      b64 "Claude stopped on an error"; body="state=error:app=$app:msg=$REPLY" ;;
  *) exit 0 ;;
esac

# An error stays until real progress (a new prompt, a new session): hooks run in
# parallel, so a tool hook from the failed turn can land after StopFailure.
dir=${REX_STATUS_DIR:-$HOME/.claude/hooks/.rex-status}
key=${REX_BLOCK//[^A-Za-z0-9_.-]/_}
mark="$dir/${key:-none}"
case "$event" in
  StopFailure) [ -d "$dir" ] || mkdir -p "$dir"; : > "$mark" ;;
  UserPromptSubmit|SessionStart|SessionEnd|Stop) [ -e "$mark" ] && rm -f "$mark" ;;
  PreToolUse|PostToolUse|PostToolUseFailure) [ -e "$mark" ] && exit 0 ;;
esac

# Claude Code runs hooks without a controlling terminal (/dev/tty fails), so write
# to the terminal of the parent Claude process. Its tty is looked up once (one ps
# launch) and cached per Claude pid.
out=${REX_STATUS_OUT:-}
if [ -z "$out" ]; then
  cache="$dir/tty-$PPID"
  [ -r "$cache" ] && read -r out < "$cache"
  if [ -z "$out" ]; then
    t=$(ps -o tty= -p "$PPID" 2>/dev/null); t=${t// /}
    case "$t" in ''|'?'|'??') out=/dev/tty ;; *) out=/dev/$t ;; esac
    [ -d "$dir" ] || mkdir -p "$dir"
    [ "$out" != /dev/tty ] && printf '%s\n' "$out" > "$cache"
  fi
fi
{ printf '\033]7501;%s\033\\' "$body" > "$out"; } 2>/dev/null
[ "$event" = SessionEnd ] && rm -f "$dir/tty-$PPID"

# Cat sticker: the Ghostty tmux card (cat, folder name, caption) in a small
# floating Rex layer at the top right, closed after a few seconds (rex-cat-layer.lua).
# REX_CATS=0 turns it off. At most one per 3 s per pane: a permission prompt fires
# both PermissionRequest and Notification.
case "$body" in
  state=done*) mood=done ;; state=blocked*) mood=ask ;; state=error*) mood=failed ;; *) mood= ;;
esac
if [ -n "$mood" ] && [ "${REX_CATS:-1}" != 0 ] && [ "$out" != /dev/tty ]; then
  here=${BASH_SOURCE[0]%/*}
  printf -v now '%(%s)T' -1 2>/dev/null || now=0
  last=0; [ -r "$dir/cat-$key" ] && read -r last < "$dir/cat-$key"
  if (( now == 0 || now - ${last:-0} >= 3 )); then
    [ -d "$dir" ] || mkdir -p "$dir"
    printf '%s\n' "$now" > "$dir/cat-$key"
    field cwd; label=${REPLY%/}; label=${label##*/}; label=${label:-claude}
    # Never write images into Claude's own pane: its TUI output interleaves with
    # them and Rex prints the base64. A floating layer has a terminal of its own.
    if [ -n "${REX_CAT_CMD:-}" ]; then
      nohup "$REX_CAT_CMD" "$mood" "$label" "$REX_BLOCK" >/dev/null 2>&1 &
    else
      rex=${REX_BIN:-rex}
      nohup "$rex" do -s "$REX_SESSION" "$here/rex-cat-layer.lua" "block=$REX_BLOCK" "mood=$mood" "label=$label" seconds=4 >/dev/null 2>&1 &
    fi
  fi
fi
