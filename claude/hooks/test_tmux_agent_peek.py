"""Checks for tmux-agent-peek.py. Run: python3 test_tmux_agent_peek.py"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location("peek", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmux-agent-peek.py"))
peek = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peek)

NOW = 10_000.0
ROWS = "\n".join([
    "working\t9900\ts\t9\ttmux-notify\t%9",
    "done\t9000\ts\t3\tlaya\t%3",
    "ask\t9950\ts\t2\tcua\t%2",
    "\t\ts\t1\tmaxwell\t%1",
    "ask\t9700\ts\t4\tartemis\t%4",
    "failed\t9990\ts\t5\tbjev\t%5",
    "done\t9800\ts\t6\tjev\t%6",
])


def test_most_urgent_first():
    peek.tmux = lambda *a: ROWS
    order = [(e[0], e[3]) for e in peek.entries(NOW)]
    assert order == [("ask", "4"), ("ask", "2"), ("failed", "5"), ("done", "3"), ("done", "6"), ("working", "9")], order


def test_line_carries_pane_and_target_for_jumping():
    line = peek.line_for(("ask", 300, "s", "4", "artemis", "%4"), 12)
    pane, target, shown = line.split("\t")
    assert (pane, target) == ("%4", "s:4") and "waiting 5m" in shown


def test_preview_drops_trailing_blank_lines():
    peek.tmux = lambda *a: "a\nb\nquestion?\n\n\n"
    out = io.StringIO()
    with redirect_stdout(out):
        peek.preview("%1", 2)
    assert out.getvalue() == "b\nquestion?\n"


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
