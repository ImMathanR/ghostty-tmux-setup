#!/usr/bin/env python3
"""Peek: every tab with an agent, most urgent first, with a live preview.

Runs inside a tmux popup (prefix + j, Cmd+J in Ghostty). Waiting tabs come
first (longest wait on top), then failures, finished tabs (oldest first) and
busy ones. Enter jumps to the tab, Esc closes.

  tmux-agent-peek.py            the picker
  tmux-agent-peek.py preview P  last screenful of pane P (used by fzf)
"""
import os
import subprocess
import sys
import time

ORDER = {"ask": 0, "failed": 1, "done": 2, "working": 3}
LOOK = {  # marker, colour (24-bit), how to describe the wait
    "ask": ("?", (255, 126, 182), "waiting {t}"),
    "failed": ("✗", (255, 90, 54), "failed {t} ago"),
    "done": ("●", (95, 215, 167), "done {t} ago"),
    "working": ("◌", (138, 138, 141), "working {t}"),
}
GREY = (110, 110, 114)


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout.rstrip("\n")


def ago(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    return "%dh%02dm" % (seconds // 3600, seconds % 3600 // 60)


def paint(rgb, text, bold=False):
    return "\x1b[%s38;2;%d;%d;%dm%s\x1b[0m" % ("1;" if bold else "", *rgb, text)


def entries(now=None):
    """(state, seconds, session, index, name, pane) for every window with an agent, most urgent first."""
    now = now or time.time()
    rows = tmux("list-windows", "-a", "-f", "#{?#{m:_*,#{session_name}},0,1}", "-F",
                "#{@agent}\t#{@agent_at}\t#{session_name}\t#{window_index}\t#{window_name}\t#{pane_id}")
    found = []
    for line in rows.splitlines():
        state, at, session, idx, name, pane = (line.split("\t") + [""] * 6)[:6]
        if state in ORDER:
            found.append((state, now - float(at) if at else 0, session, idx, name, pane))
    # waits and failures: longest first; done: oldest first; working: longest first
    return sorted(found, key=lambda e: (ORDER[e[0]], -e[1]))


def line_for(entry, width):
    state, seconds, session, idx, name, pane = entry
    mark, rgb, how = LOOK[state]
    label = ("%s:%s" % (idx, name))[:width]
    return "%s\t%s\t%s  %s  %s" % (pane, "%s:%s" % (session, idx), paint(rgb, mark, True),
                                    paint(rgb, label.ljust(width), state in ("ask", "failed")),
                                    paint(GREY, how.format(t=ago(seconds))))


def preview(pane, lines):
    """The bottom of the pane, trailing blank lines dropped, colours kept."""
    shot = tmux("capture-pane", "-ep", "-J", "-t", pane).split("\n")
    while shot and not shot[-1].strip():
        shot.pop()
    print("\n".join(shot[-lines:]))


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "preview":
        preview(sys.argv[2], int(os.environ.get("FZF_PREVIEW_LINES", "40")))
        return
    found = entries()
    if not found:
        print("\n  " + paint(GREY, "No agents running. Nothing needs you."))
        time.sleep(1.4)
        return
    width = min(22, max(len("%s:%s" % (e[3], e[4])) for e in found))
    waiting = sum(e[0] == "ask" for e in found)
    header = ("%d waiting on you" % waiting) if waiting else "nothing is waiting on you"
    fzf = subprocess.run(
        ["fzf", "--ansi", "--no-sort", "--layout=reverse", "--delimiter=\t", "--with-nth=3",
         "--header=" + header + "   enter: go   esc: close", "--header-first",
         "--prompt=peek ", "--pointer=▌", "--no-scrollbar", "--info=hidden",
         "--color=bg+:#262626,fg+:#eaeaea,hl:#FFC107,hl+:#FFC107,pointer:#FFC107,"
         "prompt:#FFC107,header:#8a8a8d,border:#333333,preview-border:#333333",
         "--preview=%s %s preview {1}" % (sys.executable, os.path.abspath(__file__)),
         "--preview-window=right,64%,border-left,follow"],
        input="\n".join(line_for(e, width) for e in found), capture_output=False,
        stdout=subprocess.PIPE, text=True)
    pick = fzf.stdout.strip()
    if pick:
        pane, target = pick.split("\t")[:2]
        tmux("switch-client", "-t", target)
        tmux("select-pane", "-t", pane)


if __name__ == "__main__":
    main()
