"""Checks for tmux-agent-anim.py frames. Run: python3 test_tmux_agent_anim.py"""
import os

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmux-agent-anim.py")).read()
src = src.split("tabs = {}")[0]
src = src.replace('lock = open(os.path.expanduser("~/.claude/hooks/.tmux-agent-anim.lock"), "a+")',
                  'lock = open(os.devnull, "w")')  # the painter records its pid in its lock
src = src.replace("fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)", "pass")
m = {"__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmux-agent-anim.py")}
exec(src, m)

TEXT = " 8:lark-website "


def luma(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def test_selected_working_tab_never_dimmer_than_selected_plain_tab():
    floor = luma(m["CURRENT"])
    for t in [k / 10 for k in range(40)]:
        for fg, _, bold, _, _ in m["target"]("working", TEXT, True, t, 0):
            assert bold, "selected tab must stay bold"
            assert luma(fg) >= floor - 1, "selected tab dimmed to %s at t=%.1f" % (fg, t)


def test_selected_failed_tab_keeps_selection_colour_and_squiggle():
    cells = m["target"]("failed", TEXT, True, 0, 1.0)
    for i, (fg, _, bold, ul, _) in enumerate(cells):
        assert fg == m["CURRENT"] and bold, "selected failed tab lost its amber"
        if 0 < i < len(TEXT) - 1:
            assert ul == m["SQUIGGLE"]


def test_unselected_failed_tab_stays_rose():
    assert all(c[0] == m["ROSE"] for c in m["target"]("failed", TEXT, False, 0, 1.0))


def shown(cells, text=TEXT):
    return "".join(ch if g is None else g for ch, (_, _, _, _, g) in zip(text, cells))


def test_guilt_trip_pleads_after_two_minutes_and_keeps_the_index():
    calm = m["target"]("ask", TEXT, False, 0, 30)
    assert shown(calm) == TEXT
    pleading = m["target"]("ask", TEXT, False, 0, 120 + 0.9)
    text = shown(pleading)
    assert text.startswith(" 8:") and text != TEXT, text
    assert any(w in text for _, ws in m["PLEAS"] for w in ws), text
    assert shown(m["target"]("ask", TEXT, False, 0, 120 + 5)) == TEXT  # between pleas


def test_guilt_trip_gets_hotter():
    def reddest(age):
        return max(c[1][0] - c[1][2] for c in [m["target"]("ask", TEXT, False, 0, age + k / 20)[0]
                                                 for k in range(40)])
    assert reddest(400) > reddest(10)


def test_done_goes_cold_but_stays_distinct_from_plain():
    fresh = m["target"]("done", TEXT, False, 0, 1)[0][0]
    cold = m["target"]("done", TEXT, False, 0, 700)[0][0]
    assert fresh == m["MINT"] or luma(fresh) > luma(cold)
    assert tuple(round(v) for v in cold) == m["MINT_COLD"] and cold != m["IDLE"]


def test_failure_shrugs_without_changing_width():
    text = " 7:laya-deploy "
    prev = m["plain"](text, False)
    goal = m["target"]("failed", text, False, 0, -1)
    cells = [m["blend"](prev, goal, i, len(text), 0.45, "failed", text) for i in range(len(text))]
    glyphs = [c[4] for c in cells]
    assert "ツ" in glyphs, glyphs
    width = sum(2 if g in m["WIDE"] else (0 if g == "" else 1) for g in glyphs)
    assert width == len(text)


def test_short_names_get_a_shorter_shrug():
    assert m["shrug_for"](" 7:asp ") is not None
    assert len(m["shrug_for"](" 7:asp ")) == len(" 7:asp ")


def test_scoreboard_leads_with_longest_wait_and_links_to_it():
    s = m["scoreboard"]([("ask", "2", "cua", 30), ("ask", "4", "artemis", 250),
                         ("working", "8", "lark-website", 9), ("done", "3", "laya", 700),
                         ("done", "6", "jev", 5)])
    assert s.index("4:artemis waiting 4m +1") < s.index("1 busy") < s.index("2 done"), s
    assert "#[range=window|4]" in s and "#[range=window|3]" in s  # done links to the oldest


def test_scoreboard_short_wait_and_failures():
    s = m["scoreboard"]([("ask", "2", "cua", 12), ("failed", "5", "bjev", 3)])
    assert "2:cua needs you" in s and "5:bjev failed" in s


def test_scoreboard_empty_when_nothing_happening():
    assert m["scoreboard"]([]) == ""


def test_react_handles_every_kind_of_event():
    # the real event path: this is where a missing global once crashed the painter
    launched = []
    m["sticker"] = lambda *a: launched.append(a)
    m["tracker"] = type("T", (), {"observe": lambda self, *a: []})()
    m["extras"].log = lambda *a: None
    m["to_ghostty"] = lambda seq: None
    events = [("working", None, "1:a", False), ("ask", "working", "2:b", False), ("ask+", None, "2:b", False),
              ("done", "working", "3:c", True), ("done+", None, "3:c", False), ("failed", "working", "4:d", False),
              ("ghosted", None, "2:b", False), ("marathon", None, "1:a", False)]
    m["react"](events, ["working", "ask", "done", "failed"], 100.0)
    assert launched and launched[0][0] == "failed", launched  # the most important sticker wins


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("pass", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", e)
    raise SystemExit(failed)
