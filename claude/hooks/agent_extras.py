"""Achievements and the day log for tmux-agent-anim.py.

Achievements are awarded at most once per day each and shown as gold stickers.
"""
import datetime
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, ".agent-log.jsonl")
UNLOCKED = os.path.join(HERE, ".achievements.json")

ACHIEVEMENTS = {
    "first_blood": ("First blood", "first task finished today"),
    "hat_trick": ("Hat trick", "3 tabs finished within a minute"),
    "herder": ("Cat herder", "5 agents working at once"),
    "ghosted": ("Ghosted", "you left {label} waiting 20 minutes"),
    "comeback": ("Comeback", "{label} failed, then pulled it off"),
    "marathon": ("Marathon", "{label} has been at it for 30 minutes"),
    "night_owl": ("Night owl", "agents still at it after midnight"),
    "flawless": ("Flawless", "no failures by 6pm"),
}
HAT_TRICK_WINDOW, HERD_SIZE = 60, 5


def log(event, label, clock=time.time, path=LOG):
    try:
        with open(path, "a") as f:
            f.write(json.dumps({"t": round(clock(), 1), "event": event, "tab": label}) + "\n")
    except OSError:
        pass


class Tracker:
    """Turns agent events into achievement awards; remembers what today already earned."""

    def __init__(self, clock=time.time, store=UNLOCKED, log_path=LOG):
        self.clock, self.store = clock, store
        self.recent_done, self.failed_tabs = [], set()
        today = self._day()
        self.failed_today = False
        try:  # a restarted painter still knows whether today had a failure
            for line in open(log_path):
                entry = json.loads(line)
                if entry.get("event") == "failed" and self._day(entry["t"]) == today:
                    self.failed_today = True
        except (OSError, ValueError, KeyError):
            pass

    def _day(self, t=None):
        return datetime.date.fromtimestamp(self.clock() if t is None else t).isoformat()

    def _award(self, key, label=""):
        try:
            unlocked = json.load(open(self.store))
        except (OSError, ValueError):
            unlocked = {}
        today = unlocked.setdefault(self._day(), [])
        if key in today:
            return None
        today.append(key)
        json.dump({self._day(): today}, open(self.store, "w"))  # older days drop off
        title, line = ACHIEVEMENTS[key]
        return title, line.format(label=label)

    def observe(self, event, label, working_now):
        """event: working/ask/done/failed or a milestone (ghosted, marathon)."""
        now = self.clock()
        hour = datetime.datetime.fromtimestamp(now).hour
        wins = []
        if event == "done":
            wins.append(self._award("first_blood"))
            self.recent_done = [t for t in self.recent_done if now - t < HAT_TRICK_WINDOW] + [now]
            if len(self.recent_done) >= 3:
                wins.append(self._award("hat_trick"))
            if label in self.failed_tabs:
                self.failed_tabs.discard(label)
                wins.append(self._award("comeback", label))
            if hour >= 18 and not self.failed_today:
                wins.append(self._award("flawless"))
        elif event == "failed":
            self.failed_tabs.add(label)
            self.failed_today = True
        elif event in ("ghosted", "marathon"):
            wins.append(self._award(event, label))
        if event in ("working", "done") and hour < 5:
            wins.append(self._award("night_owl"))
        if working_now >= HERD_SIZE:
            wins.append(self._award("herder"))
        return [w for w in wins if w]
