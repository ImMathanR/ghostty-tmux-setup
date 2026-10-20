"""Checks for tui.py. Run: python3 test_tui.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tui  # noqa: E402


def pane(**kw):
    p = {"pane_id": "%1", "text": "short\nscreen", "subagents": 0, "claude": True, "pane_active": True, "width": 80}
    p.update(kw)
    return p


def test_full_view_clears_every_row_it_does_not_fill():
    b = tui.Birdseye()
    b.tabs = [{"id": "@1", "panes": [pane()]}]
    b.full = "%1"
    rows = b.full_view(80, 10)
    assert len(rows) == 10 and all(r.endswith("\x1b[0K") for r in rows), rows


def test_card_counts_agents_once_across_panes():
    # a teammate pane shows the same "← 2 agents" as the lead: the card says 2, not 4
    tab = {"panes": [pane(subagents=2), pane(pane_id="%2", subagents=2)]}
    assert tui.subagents_of(tab) == 2


if __name__ == "__main__":
    failed = 0
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            try:
                f(); print("pass", n)
            except Exception as e:
                failed += 1; print("FAIL", n, repr(e))
    raise SystemExit(failed)
