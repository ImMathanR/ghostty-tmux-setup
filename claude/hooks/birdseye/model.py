"""Birdseye data: every tmux pane's geometry, live text (ANSI), its window's
agent state (@agent) and how many subagents it is running (one file per
subagent under ../.subagents/<pane>/, kept by tmux-agent-state.sh).
"""
import json
import os
import re
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SUBAGENTS = os.path.join(os.path.dirname(HERE), ".subagents")
SEP = "\x1e"  # record separator between captured panes
FIELDS = ["session", "window_id", "window_index", "window_name", "window_active", "pane_id", "pane_index",
          "left", "top", "width", "height", "pane_active", "command", "path", "window_width",
          "window_height", "agent", "agent_at", "birdseye", "last", "sidebar"]
FORMAT = "\t".join("#{%s}" % f for f in [
    "session_name", "window_id", "window_index", "window_name", "window_active", "pane_id", "pane_index",
    "pane_left", "pane_top", "pane_width", "pane_height", "pane_active", "pane_current_command",
    "pane_current_path", "window_width", "window_height", "@agent", "@agent_at", "@birdseye", "window_last_flag", "@sidebar"])
VERSION = re.compile(r"^\d+\.\d+\.\d+$")  # Claude's process is named after its version

def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout


def subagent_count(pane_id, now):
    folder = os.path.join(SUBAGENTS, pane_id)
    try:
        # a subagent whose stop hook never came is not shown after 2 hours
        return sum(now - os.path.getmtime(os.path.join(folder, f)) < 7200 for f in os.listdir(folder))
    except OSError:
        return 0


AGENT_ROW = re.compile(r"^\s*[⏺●◯○◉]\s+(\S+)")


def agents_on_screen(text):
    """Background agents, from the list Claude draws under its status line ("⏺ main" and then one
    row per agent). Sessions started before the subagent hooks existed never report them."""
    plain = [PLAIN.sub("", l).rstrip() for l in text.split("\n")]
    status = max((i for i, l in enumerate(plain) if "⏵⏵" in l or "shift+tab" in l), default=None)
    if status is None:
        return 0
    rows = [AGENT_ROW.match(l) for l in plain[status + 1:] if l.strip()]
    names = [m.group(1) for m in rows if m]
    return len([n for n in names if n != "main"]) if "main" in names else 0


def parse_panes(listing):
    panes = []
    for line in listing.splitlines():
        values = (line.split("\t") + [""] * len(FIELDS))[:len(FIELDS)]
        p = dict(zip(FIELDS, values))
        for k in ("left", "top", "width", "height", "window_width", "window_height", "window_index", "pane_index"):
            p[k] = int(p[k] or 0)
        p["window_active"], p["pane_active"] = p["window_active"] == "1", p["pane_active"] == "1"
        p["claude"] = bool(VERSION.match(p["command"]))
        p["birdseye"] = p["birdseye"] == "1"  # the map's own tab
        p["sidebar"] = p["sidebar"] == "1"    # the window list down the left (sidebar/)
        p["folder"] = os.path.basename(p.pop("path").rstrip("/")) or "/"
        panes.append(p)
    return panes


def hidden(session):
    """Helper sessions (birdseye's details pane runs a client of "_birdseye") are nobody's tabs."""
    return session.startswith("_")


def visible(panes):
    return [p for p in panes if not hidden(p["session"])]


def first_client(listing):
    """(session, window id) of the first real client in 'session\twindow\tname' lines."""
    for line in listing.split("\n"):
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] and not hidden(parts[0]):
            return parts[0], parts[1]
    return "", ""


def split_captures(blob):
    """'\x1e%3\n<text>\x1e%4\n<text>' -> {'%3': text, ...}"""
    out = {}
    for chunk in blob.split(SEP)[1:]:
        pane_id, _, text = chunk.partition("\n")
        out[pane_id.strip()] = text.rstrip("\n")
    return out


def snapshot():
    now = time.time()
    panes = visible(parse_panes(tmux("list-panes", "-a", "-F", FORMAT)))
    args = []
    for p in panes:  # one tmux call captures every pane
        # "#{pane_id}", not the literal id: tmux eats the "%" of "%12" in a format
        args += ["display", "-p", "-t", p["pane_id"], SEP + "#{pane_id}", ";",
                 "capture-pane", "-e", "-p", "-t", p["pane_id"], ";"]
    text = split_captures(tmux(*args[:-1])) if args else {}
    for p in panes:
        p["text"] = text.get(p["pane_id"], "")
        p["subagents"] = max(subagent_count(p["pane_id"], now), agents_on_screen(p["text"]))
        p["agent_age"] = int(now - float(p["agent_at"])) if p["agent_at"] else None
    session, window = first_client(tmux("list-clients", "-F", "#{client_session}\t#{window_id}\t#{client_name}"))
    if any(p["window_id"] == window and p["birdseye"] for p in panes):
        # looking at the map itself: "you are here" is the tab you came from
        window = next((p["window_id"] for p in panes if p["session"] == session and p["last"] == "1"), window)
    return {"now": now, "panes": panes, "client_session": session, "client_window": window,
            "score": tmux("show", "-gqv", "@agent_score")}


def focus(pane_id):
    """Switch the attached client to the pane's tab and pane."""
    target = tmux("display", "-p", "-t", pane_id, "#{session_name}:#{window_id}").strip()
    if target:
        tmux("switch-client", "-t", target, ";", "select-window", "-t", target, ";", "select-pane", "-t", pane_id)
    return bool(target)


# ── what a tab is doing, in words ──
PLAIN = re.compile(r"\x1b\[[0-9;:]*[A-Za-z]")


def content_lines(text):
    """What the agent is saying, without Claude's input box and status lines.

    Claude draws its prompt as a short box: a long rule, one to a few lines
    starting with the prompt mark, another rule, then status lines. A taller box
    is a question or permission dialog, which is content and stays.
    """
    lines = text.split("\n")
    plain = [PLAIN.sub("", l) for l in lines]
    rules = [i for i, l in enumerate(plain) if l.count("─") >= 20]
    cut = len(lines)
    if len(rules) >= 2 and rules[-1] - rules[-2] <= 5 and any(
            l.lstrip().startswith(("❯", ">", "›")) for l in plain[rules[-2] + 1:rules[-1]]):
        cut = rules[-2]
    body = lines[:cut]
    while body and not PLAIN.sub("", body[-1]).strip():
        body.pop()
    return body


def state_of(tile):
    agent, age = tile["agent"], tile["agent_age"]
    if agent == "done" and age and age > 600:
        return "cold"
    return agent or ""


def ago(s):
    if s is None:
        return ""
    return "%ds" % s if s < 60 else "%dm" % (s // 60) if s < 3600 else "%dh" % (s // 3600)


def describe(tile):
    words = {"working": "working %s", "ask": "needs you %s", "done": "done %s ago", "cold": "done %s ago",
             "failed": "failed %s ago"}
    state = state_of(tile)
    return words[state] % ago(tile["agent_age"]) if state else ""
