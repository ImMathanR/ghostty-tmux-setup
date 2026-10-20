"""Checks for ansi.py. Run: python3 test_ansi.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ansi  # noqa: E402

BLUE = "\x1b[38;2;90;160;255m"


def test_colours_survive_a_cut():
    out = ansi.clip("see " + BLUE + "run.test.js" + "\x1b[0m for details", 10)
    assert BLUE in out and ansi.plain(out) == "see run.te"
    assert out.endswith("\x1b[0m")  # colour never leaks into the next card


def test_pads_to_exact_width():
    assert ansi.visible_width(ansi.clip("hi", 8)) == 8


def test_wide_characters_count_twice_and_never_straddle():
    out = ansi.clip("ab中文", 5)          # a b 中 = 4 cells, 文 would need cells 5-6
    assert ansi.visible_width(out) == 5 and ansi.plain(out) == "ab中 "


def test_cursor_codes_are_dropped():
    out = ansi.clip("x\x1b[2Ky\x1b[10Cz", 3)
    assert ansi.plain(out) == "xyz" and "\x1b[2K" not in out and "\x1b[10C" not in out


def test_wrap_breaks_at_words_and_fits():
    lines = ansi.wrap("  one two three four five six", 12)
    assert all(ansi.visible_width(l) <= 12 for l in lines), lines
    assert [ansi.plain(l).strip() for l in lines] == ["one two", "three four", "five six"], lines


def test_wrap_keeps_the_hanging_indent_and_colour():
    lines = ansi.wrap("● " + BLUE + "alpha beta gamma delta" + "\x1b[0m", 14)
    assert ansi.plain(lines[1]).startswith("  ") and BLUE in lines[1], lines


def test_wrap_splits_a_word_longer_than_the_line():
    lines = ansi.wrap("x" * 25, 10)
    assert [len(ansi.plain(l)) for l in lines] == [10, 10, 5]


def test_unwrap_joins_lines_the_terminal_broke():
    width = 20
    lines = ["● " + "a" * 18, "  bbb ccc", "", "next para"]  # the first fills the pane width
    assert [ansi.plain(l) for l in ansi.unwrap(lines, width)] == ["● " + "a" * 18 + " bbb ccc", "", "next para"]



def test_hyperlink_ended_by_st_takes_no_width():
    # Claude Code prints URLs as OSC 8 links ending in ESC \ (not BEL): the link target is invisible
    url = "http://127.0.0.1:8813/landing.html"
    line = "reload \x1b]8;id=e42wv4;" + url + "\x1b\\" + url + "\x1b]8;;\x1b\\ to see it"
    assert ansi.visible_width(line) == len("reload " + url + " to see it")
    assert ansi.plain(line) == "reload " + url + " to see it"
    clipped = ansi.clip(line, 60)
    assert ansi.visible_width(clipped) == 60 and "8;id=" not in clipped

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
