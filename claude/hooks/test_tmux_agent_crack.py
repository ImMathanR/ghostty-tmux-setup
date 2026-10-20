"""Checks for tmux-agent-crack.py placement. Run: python3 test_tmux_agent_crack.py"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "tmux-agent-crack.py")).read().replace('if __name__ == "__main__":\n    main()', "")
m = {"__file__": os.path.join(HERE, "tmux-agent-crack.py")}
exec(src, m)

WINDOWS = [("1", "maxwell"), ("2", "cua"), ("3", "laya-deploy"), ("4", "artemis"), ("5", "bjev")]


def test_tmux_output_keeps_meaningful_spaces():
    # status-left " tas-workspace " and a " " separator are layout, not noise
    assert m["clean"](" tas-workspace \n") == " tas-workspace "
    assert m["clean"]("x\t \n").split("\t")[1] == " "


def test_tab_five_lands_on_its_own_cells():
    left = m["strip_styles"](m["clean"]("#[fg=#FFC107,bold] tas-workspace \n"))
    sep = m["clean"]("x\t \n").split("\t")[1]
    # 15 (session) + " 1:maxwell "+1 + " 2:cua "+1 + " 3:laya-deploy "+1 + " 4:artemis "+1
    assert m["tab_column"](len(left), WINDOWS, "5", sep) == 63


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
