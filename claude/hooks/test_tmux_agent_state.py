"""Drives tmux-agent-state.sh against a throwaway tmux server. Run: python3 test_tmux_agent_state.py"""
import json
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = "agentstatetest"


def tmux(*args):
    return subprocess.run(["tmux", "-L", SOCK, *args], capture_output=True, text=True).stdout.strip()


def setup():
    tmux("kill-server")
    tmux("-f", "/dev/null", "new-session", "-d", "-s", "t", "sleep 600")
    sock = tmux("display", "-p", "#{socket_path}")
    return {**os.environ, "TMUX": sock + ",0,0", "TMUX_PANE": tmux("display", "-p", "#{pane_id}")}


def hook(env, event, arg, **extra):
    subprocess.run(["sh", os.path.join(HERE, "tmux-agent-state.sh"), arg],
                   input=json.dumps({"hook_event_name": event, **extra}), text=True, env=env,
                   capture_output=True)
    return tmux("show", "-wqv", "-t", env["TMUX_PANE"], "@agent")


def test_late_tool_hook_does_not_erase_a_failure():
    env = setup()
    assert hook(env, "StopFailure", "failed") == "failed"
    assert hook(env, "PostToolUse", "working") == "failed"   # the race that hid laya-deploy's failure
    assert hook(env, "PreToolUse", "working", tool_name="Bash") == "failed"


def test_real_progress_clears_a_failure():
    env = setup()
    hook(env, "StopFailure", "failed")
    assert hook(env, "UserPromptSubmit", "working") == "working"
    hook(env, "StopFailure", "failed")
    assert hook(env, "Stop", "done") in ("done", "")          # "" when that window is on screen
    hook(env, "StopFailure", "failed")
    assert hook(env, "PreToolUse", "working", tool_name="AskUserQuestion") == "ask"


def test_tool_hooks_still_mean_working_normally():
    env = setup()
    hook(env, "Stop", "done")
    assert hook(env, "PreToolUse", "working", tool_name="Bash") == "working"


def test_subagents_are_counted_per_pane():
    env = setup()
    folder = os.path.join(HERE, ".subagents", env["TMUX_PANE"])
    hook(env, "SubagentStart", "sub", agent_id="a1")
    hook(env, "SubagentStart", "sub", agent_id="a2")
    assert sorted(os.listdir(folder)) == ["a1", "a2"]
    assert hook(env, "SubagentStart", "sub", agent_id="a3") == ""  # never paints the badge
    hook(env, "SubagentStop", "sub", agent_id="a1")
    assert sorted(os.listdir(folder)) == ["a2", "a3"]
    hook(env, "SessionEnd", "off")
    assert not os.path.exists(folder)


def pane_opt(pane, name):
    return tmux("show", "-pqv", "-t", pane, name)


def test_each_pane_keeps_its_own_state_and_tool():
    # Archipelago draws one cat per pane, so two Claudes in one window must not share a state
    env = setup()
    other = {**env, "TMUX_PANE": tmux("split-window", "-d", "-P", "-F", "#{pane_id}", "sleep 600")}
    hook(env, "PreToolUse", "working", tool_name="Bash")
    hook(other, "PreToolUse", "working", tool_name="AskUserQuestion")
    assert pane_opt(env["TMUX_PANE"], "@pane_agent") == "working"
    assert pane_opt(env["TMUX_PANE"], "@pane_agent_tool") == "Bash"
    assert pane_opt(other["TMUX_PANE"], "@pane_agent") == "ask"
    hook(other, "SessionEnd", "off")
    assert pane_opt(other["TMUX_PANE"], "@pane_agent") == ""
    assert pane_opt(env["TMUX_PANE"], "@pane_agent") == "working"


def test_subagent_count_is_on_the_pane():
    env = setup()
    hook(env, "SubagentStart", "sub", agent_id="k1")
    hook(env, "SubagentStart", "sub", agent_id="k2")
    assert pane_opt(env["TMUX_PANE"], "@pane_agent_subs") == "2"
    hook(env, "SubagentStop", "sub", agent_id="k1")
    assert pane_opt(env["TMUX_PANE"], "@pane_agent_subs") == "1"
    hook(env, "SessionEnd", "off")


if __name__ == "__main__":
    failed = 0
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print("pass", name)
                except AssertionError as e:
                    failed += 1
                    print("FAIL", name, "-", e)
    finally:
        tmux("kill-server")
    raise SystemExit(failed)
