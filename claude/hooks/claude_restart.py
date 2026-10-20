#!/usr/bin/env python3
"""Restart every Claude Code session in tmux onto the installed version, each
back in the exact conversation it was in.

  claude-restart            restart the outdated sessions; ones that are busy, waiting on
                            you, holding unsent text or running background agents/shells
                            restart by themselves as soon as they're idle (in the background)
  claude-restart --all      every session, not just outdated ones
  claude-restart --now      only the ones that are ready right now; don't wait for the rest
  claude-restart --dry-run  show the plan, touch nothing
  claude-restart --only larkup [--only 7:previz]   just those windows

A restart types /exit into the session's own pane, waits for Claude to quit, and
runs the same command it was started with plus --resume <its conversation id>,
in its folder: same pane, same flags, same conversation. Each Claude's own record
(~/.claude/sessions/<pid>.json) gives its pane, conversation, folder and status.
Progress goes to tmux messages and ~/.claude/hooks/.restart.log.
"""
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "birdseye"))
import model  # noqa: E402  (agents_on_screen: the agent rows Claude lists under its status line)

SESSIONS = os.path.expanduser("~/.claude/sessions")
LOG = os.path.join(HERE, ".restart.log")
LOCK = os.path.join(HERE, ".restart.lock")
WAIT_UP_TO = 3 * 3600
DROP_WITH_VALUE = {"-r", "--resume", "--session-id"}
DROP = {"-c", "--continue"}


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout.strip()


def log(text):
    line = time.strftime("%H:%M:%S ") + text
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


# ── deciding ──
def resume_argv(argv, session_id):
    """The command it was started with, pointed at its own conversation."""
    out, skip = [], False
    for k, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a in DROP or any(a.startswith(f + "=") for f in DROP_WITH_VALUE | DROP):
            continue
        if a in DROP_WITH_VALUE:
            nxt = argv[k + 1] if k + 1 < len(argv) else ""
            skip = bool(nxt) and not nxt.startswith("-")    # -r alone opens the picker; -r <id> names one
            continue
        out.append(a)
    return out + ["--resume", session_id]


DIM = re.compile(r"\x1b\[2m.*?(?=\x1b\[(?:0|22)?m|$)")   # a dim run: Claude's placeholder hint
ESC = re.compile(r"\x1b\[[0-9;:]*[A-Za-z]")


def draft(screen):
    """Unsent text in Claude's input box (between its last two long rules), else ''.
    screen is captured with its styling: the dim placeholder ("Try ...") isn't text you typed."""
    lines = screen.split("\n")
    rules = [i for i, l in enumerate(lines) if ESC.sub("", l).count("─") >= 20]
    if len(rules) < 2:
        return ""
    box = [ESC.sub("", DIM.sub("", l)) for l in lines[rules[-2] + 1:rules[-1]]]
    text = " ".join(l.strip().lstrip("❯>").strip() for l in box)
    return " ".join(text.replace("\xa0", " ").split())


def ready(s):
    return s["status"] == "idle" and not s["draft"] and not s["agents"]


def why(s):
    if s["status"] != "idle":
        return {"busy": "busy", "shell": "running a shell command"}.get(s["status"], s["status"])
    if s["draft"]:
        return "has unsent text in its input box"
    if s["agents"]:
        return "%d background agents running" % s["agents"]
    return "ready"


def plan(sessions, installed, everything=False):
    """[(session, "restart" | "wait")] for the sessions in tmux that should move to installed."""
    out = []
    for s in sessions:
        if s["kind"] != "interactive" or not s["pane"]:
            continue
        if everything or s["version"] != installed:
            out.append((s, "restart" if ready(s) else "wait"))
    return out


# ── looking ──
def installed_version():
    out = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.split()
    return out[0] if out else ""


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def sessions():
    found = []
    for name in os.listdir(SESSIONS) if os.path.isdir(SESSIONS) else []:
        if not name.endswith(".json"):
            continue
        try:
            info = json.load(open(os.path.join(SESSIONS, name)))
        except (OSError, ValueError):
            continue
        if not alive(info.get("pid")) or not info.get("sessionId"):
            continue
        pane = (info.get("tmux") or "").rpartition(".")[2]
        pane = pane if pane.startswith("%") and tmux("display", "-p", "-t", pane, "#{pane_id}") == pane else None
        screen = tmux("capture-pane", "-p", "-e", "-t", pane) if pane else ""
        argv = shlex.split(subprocess.run(["ps", "-o", "args=", "-p", str(info["pid"])],
                                          capture_output=True, text=True).stdout.strip() or "claude")
        found.append({"pid": info["pid"], "sessionId": info["sessionId"], "version": info.get("version", ""),
                      "status": info.get("status", ""), "kind": info.get("kind", ""), "pane": pane,
                      "name": info.get("name") or "", "cwd": info.get("cwd") or os.path.expanduser("~"),
                      "argv": argv, "draft": draft(screen), "agents": model.agents_on_screen(screen),
                      "where": tmux("display", "-p", "-t", pane, "#{window_index}:#{window_name}") if pane else ""})
    return found


def fresh(session_id):
    return next((s for s in sessions() if s["sessionId"] == session_id), None)


# ── doing ──
def restart(s, installed):
    """Quit it in its own pane and bring the same conversation back; True when it's back."""
    cmd = shlex.join(resume_argv(s["argv"], s["sessionId"]))
    if tmux("display", "-p", "-t", s["pane"], "#{pane_pid}") == str(s["pid"]):
        # Claude is the pane's own process (a crash restore): quitting would close the pane
        tmux("respawn-pane", "-k", "-t", s["pane"], "-c", s["cwd"], cmd + "; exec ${SHELL:-zsh} -l")
    else:
        tmux("send-keys", "-t", s["pane"], "-l", "/exit")
        time.sleep(0.4)
        tmux("send-keys", "-t", s["pane"], "Enter")
        for _ in range(100):
            if not alive(s["pid"]):
                break
            time.sleep(0.2)
        else:
            log("%s: Claude didn't quit after /exit; left it alone" % s["where"])
            return False
        time.sleep(0.5)
        tmux("send-keys", "-t", s["pane"], "-l", "cd %s && %s" % (shlex.quote(s["cwd"]), cmd))
        tmux("send-keys", "-t", s["pane"], "Enter")
    for _ in range(90):
        time.sleep(0.5)
        back = fresh(s["sessionId"])
        if back and back["pid"] != s["pid"]:
            log("%s: back in its conversation on %s" % (s["where"], back["version"]))
            tmux("display-message", "claude-restart: %s is back on %s" % (s["where"], back["version"]))
            return True
    log("%s: restarted, but its conversation hasn't reappeared yet; check the pane" % s["where"])
    return False


def run(todo, installed, wait):
    """Restart what's ready; keep checking the rest until they are (or WAIT_UP_TO passes)."""
    pending, start = {s["sessionId"]: s for s, _ in todo}, time.time()
    while pending:
        for sid in list(pending):
            s = fresh(sid)
            if s is None:
                log("%s: closed before it could restart" % pending.pop(sid)["where"])
            elif ready(s):
                restart(s, installed)
                pending.pop(sid)
        if not wait or not pending or time.time() - start > WAIT_UP_TO:
            break
        time.sleep(5)
    for s in pending.values():
        log("%s: not restarted (%s)" % (s["where"], why(fresh(s["sessionId"]) or s)))


def main(args):
    installed = installed_version()
    todo = plan(sessions(), installed, everything="--all" in args)
    only = [args[k + 1] for k, a in enumerate(args[:-1]) if a == "--only"]
    if only:
        todo = [t for t in todo if any(o in (t[0]["where"], t[0]["where"].partition(":")[2], t[0]["name"]) for o in only)]
    if not todo:
        print("Every Claude in tmux is already on %s." % installed)
        return
    print("Installed: %s" % installed)
    for s, action in sorted(todo, key=lambda t: t[0]["where"]):
        note = "now" if action == "restart" else "when idle: " + why(s)
        print("  %-28s %-9s %s" % (s["where"] or s["name"], s["version"], note))
    if "--dry-run" in args:
        return
    if "--now" in args:
        run([t for t in todo if t[1] == "restart"], installed, wait=False)
        return
    # the rest happens in the background, so it can wait for busy sessions (even the one that ran it)
    if os.fork():
        print("Restarting in the background; progress in tmux messages and %s" % LOG)
        return
    os.setsid()
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log("another claude-restart is already running; leaving it to that one")
            return
        sys.stdout = sys.stderr = open(os.devnull, "w")
        run(todo, installed, wait=True)


if __name__ == "__main__":
    main(sys.argv[1:])
