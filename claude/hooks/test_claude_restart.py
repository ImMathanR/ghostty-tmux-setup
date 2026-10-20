"""Checks for claude_restart.py. Run: python3 test_claude_restart.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_restart as cr  # noqa: E402


def test_resume_keeps_flags_and_resumes_the_exact_conversation():
    assert cr.resume_argv(["claude", "--dangerously-skip-permissions", "-r"], "abc") == \
        ["claude", "--dangerously-skip-permissions", "--resume", "abc"]
    assert cr.resume_argv(["claude", "-r", "old-id", "--model", "opus"], "abc") == \
        ["claude", "--model", "opus", "--resume", "abc"]
    assert cr.resume_argv(["/usr/local/bin/claude", "--continue", "--resume=x", "-c"], "abc") == \
        ["/usr/local/bin/claude", "--resume", "abc"]


def s(**kw):
    d = {"pid": 1, "sessionId": "id", "version": "2.1.289", "status": "idle", "kind": "interactive",
         "pane": "%1", "name": "zap", "draft": "", "agents": 0}
    d.update(kw)
    return d


def test_plan_restarts_idle_outdated_sessions_and_waits_for_the_rest():
    plan = cr.plan([s(), s(pane="%2", status="busy"), s(pane="%3", status="shell"),
                    s(pane="%4", version="2.1.294"), s(pane="%5", draft="half a thought"),
                    s(pane="%6", agents=2), s(pane=None, kind="bg")], installed="2.1.294")
    got = {p["pane"]: action for p, action in plan}
    assert got == {"%1": "restart", "%2": "wait", "%3": "wait", "%5": "wait", "%6": "wait"}, got


def test_plan_all_includes_up_to_date_sessions():
    plan = cr.plan([s(version="2.1.294")], installed="2.1.294", everything=True)
    assert [a for _, a in plan] == ["restart"]


def test_why_says_what_it_is_waiting_for():
    assert "busy" in cr.why(s(status="busy"))
    assert "unsent" in cr.why(s(draft="hi"))
    assert "2 background agents" in cr.why(s(agents=2))


def test_draft_is_the_text_in_claudes_input_box():
    rule = "─" * 40
    assert cr.draft(f"answer\n{rule}\n❯ \xa0\n{rule}\n  status") == ""
    assert cr.draft(f"answer\n{rule}\n❯ fix the login bug\n{rule}\n  status") == "fix the login bug"
    assert cr.draft("$ ls\nfoo") == ""


def test_the_dim_placeholder_is_not_unsent_text():
    # exact bytes from a fresh Claude 2.1.294 (placeholder) and one with typed text
    rule = "─" * 40
    placeholder = '\x1b[39m❯\xa0\x1b[2mTry "fix lint errors"\x1b[0m'
    typed = "\x1b[39m❯\xa0hello draft"
    assert cr.draft(f"{rule}\n{placeholder}\n{rule}\nstatus") == ""
    assert cr.draft(f"{rule}\n{typed}\n{rule}\nstatus") == "hello draft"


if __name__ == "__main__":
    failed = 0
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            try:
                f(); print("pass", n)
            except Exception as e:
                failed += 1; print("FAIL", n, repr(e))
    raise SystemExit(failed)
