"""Checks for birdseye's content extraction. Run: python3 test_render.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as render  # noqa: E402

RULE = "─" * 60
CLAUDE = "\n".join([
    "  Step 3 changes the live agent, so it waits for your yes. Should I start?",
    "",
    "✻ Baked for 23s · done 3:41 PM",
    "",
    RULE, "❯ yess! first tell me what's", RULE,
    "    [Opus 5.5] 10% context",
    "  ⏵⏵ bypass permissions on (shift+tab to cycle)",
])
DIALOG = "\n".join([
    "  I need to run a command.",
    RULE,
    " Bash command",
    "   rm -rf build",
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. No",
    RULE,
])


def test_input_box_and_status_are_dropped():
    body = render.content_lines(CLAUDE)
    assert body[-1].startswith("✻ Baked"), body
    assert not any("context" in l or "❯" in l for l in body)


def test_a_permission_dialog_is_kept():
    body = render.content_lines(DIALOG)
    assert any("Do you want to proceed?" in l for l in body) and any("1. Yes" in l for l in body)


def test_plain_shell_keeps_everything_but_trailing_blanks():
    assert render.content_lines("$ ls\na b c\n\n\n") == ["$ ls", "a b c"]


def test_ansi_does_not_confuse_the_cut():
    coloured = CLAUDE.replace(RULE, "\x1b[38;5;240m" + RULE + "\x1b[0m")
    assert render.content_lines(coloured)[-1].startswith("✻ Baked")



def test_hidden_helper_sessions_are_ignored():
    # birdseye's details pane is a client of a hidden "_birdseye" session that shares every window
    listing = "_birdseye\t@7\t/dev/ttys030\ntas-demo\t@12\t/dev/ttys000"
    assert render.first_client(listing) == ("tas-demo", "@12")
    rows = render.parse_panes("_birdseye\t@7\t7\tlarkup\t1\t%22\t1\t0\t0\t80\t24\t1\tzsh\t/w\t80\t24\t\t\t\t\t\n"
                             "tas\t@7\t7\tlarkup\t1\t%22\t1\t0\t0\t80\t24\t1\tzsh\t/w\t80\t24\t\t\t\t\t\n")
    assert [p["session"] for p in render.visible(rows)] == ["tas"]



def test_agents_are_the_rows_under_claudes_status_line():
    status = "  ⏵⏵ bypass permissions on · 2 shells · ← 2 agents"
    screen = ("  Ran 2 shell commands\n" + status + "\n\n  ⏺ main\n"
              "  ◯ general-purpose  Counting chapter… 10m 34s · ↓ 239.2k tokens\n"
              "  ◯ app-installer    Install a list o…                   17m 49s")
    assert render.agents_on_screen(screen) == 2
    # "← 2 agents" alone is on every Claude, busy or not: it is not a count of running agents
    assert render.agents_on_screen("❯ \n    [Opus 5.5] 9% context\n" + status) == 0
    assert render.agents_on_screen("● main thing is done\n◯ a list item  in the answer") == 0

if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("pass", name)
            except Exception as e:
                failed += 1
                print("FAIL", name, "-", e)
    raise SystemExit(failed)
