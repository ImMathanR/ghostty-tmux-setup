#!/usr/bin/env python3
"""Adds this repo's Claude Code hooks to a settings.json, keeping everything else.

  merge_settings.py [settings.json]   (default: ~/.claude/settings.json)

Hook entries that already call one of our scripts (from any path, such as an
older absolute one) are replaced, so running this again never duplicates
them. Other hooks and settings stay as they are. The old file is kept as
settings.json.bak-<timestamp>.
"""
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ("tmux-agent-state.sh", "random-color.sh")
OURS = re.compile(r"\.claude/hooks/(%s)\b" % "|".join(re.escape(s) for s in SCRIPTS))


def ours(group):
    return any(OURS.search(h.get("command", "")) for h in group.get("hooks", []))


def merge(settings, hooks):
    """settings with every group in hooks added, after dropping our old groups."""
    current = settings.setdefault("hooks", {})
    for event, groups in hooks.items():
        kept = [g for g in current.get(event, []) if not ours(g)]
        current[event] = kept + json.loads(json.dumps(groups))
    return settings


def main(path):
    hooks = json.load(open(os.path.join(HERE, "settings.hooks.json")))["hooks"]
    settings = {}
    if os.path.exists(path):
        with open(path) as f:
            text = f.read()
        settings = json.loads(text) if text.strip() else {}
        shutil.copy2(path, "%s.bak-%s" % (path, time.strftime("%Y%m%d%H%M%S")))
    else:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    merged = merge(settings, hooks)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/settings.json"))
