"""Checks for achievements (agent_extras.py) and sleep mode. Run: python3 test_agent_extras.py"""
import datetime
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agent_extras as extras  # noqa: E402

TMP = tempfile.mkdtemp()


def tracker_at(hour, minute=0, log_lines=()):
    clock = [datetime.datetime(2026, 9, 28, hour, minute).timestamp()]
    store, log = os.path.join(TMP, "unlocked-%s.json" % id(clock)), os.path.join(TMP, "log-%s.jsonl" % id(clock))
    with open(log, "w") as f:
        for line in log_lines:
            f.write(json.dumps(line) + "\n")
    t = extras.Tracker(clock=lambda: clock[0], store=store, log_path=log)
    return t, clock


def titles(wins):
    return [w[0] for w in wins]


def test_first_blood_once_per_day():
    t, _ = tracker_at(10)
    assert titles(t.observe("done", "3:laya", 1)) == ["First blood"]
    assert titles(t.observe("done", "4:artemis", 1)) == []


def test_hat_trick_needs_three_within_a_minute():
    t, clock = tracker_at(10)
    t.observe("done", "1:a", 0)
    clock[0] += 70
    t.observe("done", "2:b", 0)
    clock[0] += 20
    assert "Hat trick" not in titles(t.observe("done", "3:c", 0))
    clock[0] += 20
    assert "Hat trick" in titles(t.observe("done", "4:d", 0))


def test_comeback_after_a_failure_on_the_same_tab():
    t, _ = tracker_at(10)
    t.observe("failed", "5:bjev", 0)
    wins = t.observe("done", "5:bjev", 0)
    assert ("Comeback", "5:bjev failed, then pulled it off") in wins


def test_flawless_only_without_failures_and_after_six():
    t, _ = tracker_at(18, 30)
    assert "Flawless" in titles(t.observe("done", "1:a", 0))
    t2, _ = tracker_at(18, 30, [{"t": datetime.datetime(2026, 9, 28, 9).timestamp(), "event": "failed", "tab": "x"}])
    assert "Flawless" not in titles(t2.observe("done", "1:a", 0))  # remembered across restarts
    t3, _ = tracker_at(15)
    assert "Flawless" not in titles(t3.observe("done", "1:a", 0))


def test_night_owl_herder_and_milestones():
    t, _ = tracker_at(1)
    assert "Night owl" in titles(t.observe("working", "1:a", 1))
    t2, _ = tracker_at(11)
    assert "Cat herder" in titles(t2.observe("working", "1:a", 5))
    assert titles(t2.observe("ghosted", "2:cua", 0)) == ["Ghosted"]
    assert t2.observe("marathon", "8:lark", 0)[0] == ("Marathon", "8:lark has been at it for 30 minutes")


# ── sleep mode, from the painter ──
src = open(os.path.join(HERE, "tmux-agent-anim.py")).read().split("tabs = {}")[0]
src = src.replace('lock = open(os.path.expanduser("~/.claude/hooks/.tmux-agent-anim.lock"), "a+")',
                  'lock = open(os.devnull, "w")')  # the painter records its pid in its lock
src = src.replace("fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)", "pass")
src = src.replace("tracker = extras.Tracker()", "tracker = None")
m = {"__file__": os.path.join(HERE, "tmux-agent-anim.py")}
exec(src, m)


def test_sleeping_tabs_breathe_but_the_selected_one_stays_amber():
    text = " 3:laya-deploy "
    shades = {m["target"]("sleep", text, False, t / 4, 0)[0][0] for t in range(20)}
    assert len(shades) > 5  # it moves
    assert all(m["target"]("sleep", text, True, t, 0)[0][0] == m["CURRENT"] for t in range(5))


def test_zzz_drifts_and_keeps_its_width():
    import re
    frames = [m["zzz"](t / 3) for t in range(12)]
    widths = {len(re.sub(r"#\[[^]]*\]", "", f)) for f in frames}
    assert widths == {9} and len(set(frames)) > 3, (widths, frames[:2])
    assert m["scoreboard"]([], snooze=1.0).count("z") + m["scoreboard"]([], snooze=1.0).count("Z") == 3


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("pass", name)
            except Exception as e:
                failed += 1
                print("FAIL", name, "-", type(e).__name__, e)
    raise SystemExit(failed)
