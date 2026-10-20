#!/usr/bin/env python3
"""Remembers which Claude conversation runs in which tmux pane, so a crash
restore (tmux-resurrect) can reopen the exact conversation.

  claude_sessions.py record    hook input JSON on stdin; needs $TMUX_PANE
  claude_sessions.py resume    exec claude --resume <id> for this pane
  claude_sessions.py rekey     re-file running conversations under their panes' current
                               coordinates (after the sidebar shifts pane numbers)

Keys are "session:window.pane", the coordinates tmux-resurrect restores.
"""
import json
import os
import subprocess
import sys
import time

MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmux-claude-sessions.json")
FLAGS = ["--dangerously-skip-permissions"]  # how Claude is always started here


def load(path=MAP):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {}


def record(key, session_id, cwd, path=MAP, clock=time.time):
    sessions = load(path)
    sessions[key] = {"session_id": session_id, "cwd": cwd, "seen": round(clock())}
    tmp = path + ".tmp"
    json.dump(sessions, open(tmp, "w"), indent=1)
    os.replace(tmp, path)  # a crash mid-write never leaves half a file


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def rekey(sessions=os.path.expanduser("~/.claude/sessions"), path=MAP, where=None):
    """Claude's own session files know each running conversation's pane ("tmux": "s:@win.%pane")."""
    where = where or (lambda pane: subprocess.run(
        ["tmux", "display", "-p", "-t", pane, "#{session_name}:#{window_index}.#{pane_index}"],
        capture_output=True, text=True).stdout.strip())
    found = {}
    for name in os.listdir(sessions):
        if not name.endswith(".json"):
            continue
        try:
            info = json.load(open(os.path.join(sessions, name)))
        except (OSError, ValueError):
            continue
        pane = (info.get("tmux") or "").rpartition(".")[2]
        if pane.startswith("%") and info.get("sessionId") and alive(info.get("pid")):
            key = where(pane)
            if key:
                found[key] = (info["sessionId"], info.get("cwd", ""))
    moved = {sid for sid, _ in found.values()}
    kept = {k: v for k, v in load(path).items() if v.get("session_id") not in moved and k not in found}
    tmp = path + ".tmp"
    now = round(time.time())
    kept.update({k: {"session_id": sid, "cwd": cwd, "seen": now} for k, (sid, cwd) in found.items()})
    json.dump(kept, open(tmp, "w"), indent=1)
    os.replace(tmp, path)


def resume_command(key, path=MAP):
    """The claude command that reopens this pane's conversation."""
    entry = load(path).get(key)
    if entry and entry.get("session_id"):
        return ["claude", *FLAGS, "--resume", entry["session_id"]]
    return ["claude", *FLAGS, "--continue"]  # newest conversation in this folder


def pane_key():
    out = subprocess.run(["tmux", "display", "-p", "-t", os.environ.get("TMUX_PANE", ""),
                          "#{session_name}:#{window_index}.#{pane_index}"], capture_output=True, text=True)
    return out.stdout.strip()


def main():
    if sys.argv[1:] == ["record"]:
        if not os.environ.get("TMUX_PANE"):
            return
        hook = json.loads(sys.stdin.read() or "{}")
        if hook.get("session_id") and not hook.get("agent_id"):
            record(pane_key(), hook["session_id"], hook.get("cwd", ""))
    elif sys.argv[1:] == ["rekey"]:
        rekey()
    elif sys.argv[1:] == ["resume"]:
        cmd = resume_command(pane_key())
        os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
