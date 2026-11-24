"""Tests for rex-agent-status.sh: Claude Code hook events -> Rex Program Status (OSC 7501).

Run: python3 test_rex_agent_status.py
The script writes to $REX_STATUS_OUT when set (tests), else to the pane's tty.
"""
import base64, json, os, subprocess, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_SH = os.path.join(HERE, "tmux-agent-state.sh")


def b64(s):
    return base64.b64encode(s.encode()).decode()


class RexAgentStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "tty")
        open(self.out, "w").close()

    def run_hook(self, arg, payload, block="block:test-1"):
        env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
        env.update(REX_SESSION="session:test", REX_BLOCK=block, REX_STATUS_OUT=self.out,
                   REX_STATUS_DIR=self.tmp, REX_CATS="0")
        subprocess.run(["bash", STATE_SH, arg], input=json.dumps(payload).encode(),
                       env=env, check=True, timeout=20)
        with open(self.out) as f:
            data = f.read()
        open(self.out, "w").close()
        return data

    def osc(self, body):
        return "\x1b]7501;" + body + "\x1b\\"

    def test_prompt_is_working(self):
        got = self.run_hook("working", {"hook_event_name": "UserPromptSubmit"})
        self.assertEqual(got, self.osc("state=working:app=claude-code"))

    def test_tool_use_is_working_with_tool_name(self):
        got = self.run_hook("working", {"hook_event_name": "PreToolUse", "tool_name": "Bash"})
        self.assertEqual(got, self.osc("state=working:app=claude-code:msg=" + b64("Bash")))

    def test_permission_request_is_blocked_permission(self):
        got = self.run_hook("ask", {"hook_event_name": "PermissionRequest", "tool_name": "Bash"})
        self.assertEqual(got, self.osc("state=blocked:kind=permission:app=claude-code:msg=" + b64("Allow Bash?")))

    def test_ask_user_question_is_blocked_question(self):
        got = self.run_hook("working", {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion"})
        self.assertEqual(got, self.osc("state=blocked:kind=question:app=claude-code:msg=" + b64("Claude has a question")))

    def test_idle_notification_is_ignored(self):
        got = self.run_hook("ask", {"hook_event_name": "Notification", "notification_type": "idle_prompt"})
        self.assertEqual(got, "")

    def test_permission_notification_is_blocked(self):
        got = self.run_hook("ask", {"hook_event_name": "Notification", "notification_type": "permission_prompt"})
        self.assertTrue(got.startswith("\x1b]7501;state=blocked:kind=permission:app=claude-code"), got)

    def test_stop_is_done(self):
        got = self.run_hook("done", {"hook_event_name": "Stop"})
        self.assertEqual(got, self.osc("state=done:app=claude-code:msg=" + b64("Claude finished")))

    def test_failure_is_error_and_sticks_over_late_tool_hooks(self):
        got = self.run_hook("failed", {"hook_event_name": "StopFailure"})
        self.assertEqual(got, self.osc("state=error:app=claude-code:msg=" + b64("Claude stopped on an error")))
        late = self.run_hook("working", {"hook_event_name": "PostToolUse", "tool_name": "Bash"})
        self.assertEqual(late, "", "a late tool hook must not replace the error")
        nxt = self.run_hook("working", {"hook_event_name": "UserPromptSubmit"})
        self.assertEqual(nxt, self.osc("state=working:app=claude-code"))

    def test_session_start_is_idle_and_end_clears(self):
        self.assertEqual(self.run_hook("off", {"hook_event_name": "SessionStart"}),
                         self.osc("state=idle:app=claude-code"))
        self.assertEqual(self.run_hook("off", {"hook_event_name": "SessionEnd"}), self.osc("state=clear"))

    def test_subagent_events_are_ignored(self):
        self.assertEqual(self.run_hook("sub", {"hook_event_name": "SubagentStart", "agent_id": "a1"}), "")
        self.assertEqual(self.run_hook("working", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                   "agent_id": "a1"}), "")

    def test_writes_to_the_parent_claude_terminal_when_hook_has_no_tty(self):
        # Claude Code runs hooks without a controlling terminal; the hook must write to
        # the terminal of its parent (Claude), cached per parent pid as tty-<pid>.
        env = {k: v for k, v in os.environ.items()
               if k not in ("TMUX", "TMUX_PANE", "REX_STATUS_OUT")}
        env.update(REX_SESSION="session:test", REX_BLOCK="block:t2", REX_STATUS_DIR=self.tmp, REX_CATS="0")
        with open(os.path.join(self.tmp, "tty-%d" % os.getpid()), "w") as f:
            f.write(self.out)
        subprocess.run(["bash", STATE_SH, "done"], input=b'{"hook_event_name":"Stop"}',
                       env=env, check=True, timeout=20, start_new_session=True)
        with open(self.out) as f:
            self.assertEqual(f.read(), self.osc("state=done:app=claude-code:msg=" + b64("Claude finished")))

    def cat_calls(self, arg, payload, cats="1"):
        log = os.path.join(self.tmp, "catlog")
        fake = os.path.join(self.tmp, "fakecat.sh")
        with open(fake, "w") as f:
            f.write('#!/bin/bash\necho "$@" >> %s\n' % log)
        os.chmod(fake, 0o755)
        env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
        env.update(REX_SESSION="session:test", REX_BLOCK="block:cat", REX_STATUS_OUT=self.out,
                   REX_STATUS_DIR=self.tmp, REX_CAT_CMD=fake, REX_CATS=cats)
        subprocess.run(["bash", STATE_SH, arg], input=json.dumps(payload).encode(),
                       env=env, check=True, timeout=20)
        for _ in range(50):  # the launcher runs detached
            if os.path.exists(log):
                break
            import time; time.sleep(0.1)
        return open(log).read().split("\n")[0].split() if os.path.exists(log) else []

    def test_done_floats_a_done_cat(self):
        args = self.cat_calls("done", {"hook_event_name": "Stop", "cwd": os.path.join(self.tmp, "project")})
        # mood, label, Rex block: drawn in a floating layer, never written into Claude's own pane
        self.assertEqual(args, ["done", "project", "block:cat"])

    def test_permission_floats_an_ask_cat_and_error_a_failed_cat(self):
        self.assertEqual(self.cat_calls("ask", {"hook_event_name": "PermissionRequest", "tool_name": "Bash"})[0], "ask")
        os.remove(os.path.join(self.tmp, "catlog"))
        os.remove(os.path.join(self.tmp, "cat-block_cat"))  # reset the 3 s limit
        self.assertEqual(self.cat_calls("failed", {"hook_event_name": "StopFailure"})[0], "failed")

    def test_one_cat_per_prompt_even_when_two_events_fire(self):
        self.cat_calls("ask", {"hook_event_name": "PermissionRequest", "tool_name": "Bash"})
        os.remove(os.path.join(self.tmp, "catlog"))
        self.assertEqual(self.cat_calls("ask", {"hook_event_name": "Notification",
                                                "notification_type": "permission_prompt"}), [])

    def test_working_and_cats_off_float_nothing(self):
        self.assertEqual(self.cat_calls("working", {"hook_event_name": "UserPromptSubmit"}), [])
        self.assertEqual(self.cat_calls("done", {"hook_event_name": "Stop"}, cats="0"), [])

    def test_outside_rex_nothing_is_written(self):
        env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE", "REX_SESSION")}
        env.update(REX_STATUS_OUT=self.out)
        subprocess.run(["bash", STATE_SH, "working"], input=b'{"hook_event_name":"UserPromptSubmit"}',
                       env=env, check=True, timeout=20)
        self.assertEqual(open(self.out).read(), "")

    def test_direct_status_hook_is_also_off_outside_rex(self):
        env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE", "REX_SESSION")}
        env.update(REX_STATUS_OUT=self.out, REX_STATUS_DIR=self.tmp, REX_CATS="0")
        subprocess.run(["bash", os.path.join(HERE, "rex-agent-status.sh"), "working"],
                       input=b'{"hook_event_name":"UserPromptSubmit"}', env=env, check=True, timeout=20)
        self.assertEqual(open(self.out).read(), "")

    def test_layer_launcher_finds_rex_on_path(self):
        fake = os.path.join(self.tmp, "rex")
        log = os.path.join(self.tmp, "rexlog")
        with open(fake, "w") as f:
            f.write('#!/bin/sh\nprintf "%s\\n" "$@" > "$REX_TEST_LOG"\n')
        os.chmod(fake, 0o755)
        env = {k: v for k, v in os.environ.items()
               if k not in ("TMUX", "TMUX_PANE", "REX_BIN", "REX_CAT_CMD")}
        env.update(REX_SESSION="session:test", REX_BLOCK="block:cat", REX_STATUS_OUT=self.out,
                   REX_STATUS_DIR=self.tmp, REX_CATS="1", REX_TEST_LOG=log,
                   PATH=self.tmp + os.pathsep + env["PATH"])
        subprocess.run(["bash", STATE_SH, "done"], input=b'{"hook_event_name":"Stop"}',
                       env=env, check=True, timeout=20)
        import time
        for _ in range(50):
            if os.path.exists(log):
                break
            time.sleep(0.1)
        self.assertTrue(os.path.exists(log), "the detached launcher must find rex on PATH")
        self.assertEqual(open(log).read().splitlines(),
                         ["do", "-s", "session:test", os.path.join(HERE, "rex-cat-layer.lua"),
                          "block=block:cat", "mood=done", "label=claude", "seconds=4"])


if __name__ == "__main__":
    unittest.main()
