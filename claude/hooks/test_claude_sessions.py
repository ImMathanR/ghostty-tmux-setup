"""Checks for claude_sessions.py. Run: python3 test_claude_sessions.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_sessions as cs  # noqa: E402

MAP = os.path.join(tempfile.mkdtemp(), "map.json")


def test_restore_reopens_the_exact_conversation():
    cs.record("tas-demo:2.1", "c7573514-2c00", "/srv/work/cua", path=MAP)
    assert cs.resume_command("tas-demo:2.1", path=MAP) == \
        ["claude", "--dangerously-skip-permissions", "--resume", "c7573514-2c00"]


def test_latest_conversation_in_a_pane_wins():
    cs.record("s:4.1", "old", "/a", path=MAP)
    cs.record("s:4.1", "new", "/a", path=MAP)
    assert cs.resume_command("s:4.1", path=MAP)[-1] == "new"
    assert json.load(open(MAP))["tas-demo:2.1"]["session_id"] == "c7573514-2c00"  # others kept


def test_unknown_pane_falls_back_to_newest_in_folder():
    assert cs.resume_command("s:9.1", path=MAP) == ["claude", "--dangerously-skip-permissions", "--continue"]


def test_corrupt_map_does_not_break_restore():
    bad = MAP + ".bad"
    open(bad, "w").write("{half")
    assert cs.resume_command("s:1.1", path=bad)[-1] == "--continue"



def test_rekey_follows_panes_that_moved():
    # the sidebar split in front of a Claude pane: 7.1 became 7.2; Claude's own session file knows the pane
    folder = tempfile.mkdtemp()
    json.dump({"pid": os.getpid(), "sessionId": "abc", "cwd": "/w/lark", "tmux": "tas:@11.%17"},
              open(os.path.join(folder, "123.json"), "w"))
    json.dump({"pid": 999999, "sessionId": "gone", "cwd": "/w", "tmux": "tas:@2.%3"},
              open(os.path.join(folder, "124.json"), "w"))     # not running any more
    m = os.path.join(tempfile.mkdtemp(), "map.json")
    cs.record("tas:7.1", "abc", "/w/lark", path=m)
    cs.rekey(sessions=folder, path=m, where=lambda pane: {"%17": "tas:7.2"}.get(pane, ""))
    saved = json.load(open(m))
    assert saved["tas:7.2"]["session_id"] == "abc"
    assert "tas:7.1" not in saved or saved["tas:7.1"]["session_id"] != "abc"
    assert not any(v["session_id"] == "gone" for v in saved.values())

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
