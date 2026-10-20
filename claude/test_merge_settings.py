import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge_settings as ms  # noqa: E402

OURS = json.load(open(os.path.join(HERE, "settings.hooks.json")))["hooks"]


def commands(settings, event):
    return [h["command"] for g in settings.get("hooks", {}).get(event, []) for h in g["hooks"]]


def test_adds_every_event_to_empty_settings():
    out = ms.merge({}, OURS)
    assert set(out["hooks"]) == set(OURS)
    assert commands(out, "Stop") == ['bash "$HOME/.claude/hooks/tmux-agent-state.sh" done']


def test_keeps_unrelated_hooks_and_settings():
    other = {"matcher": "*", "hooks": [{"type": "command", "command": "flux-hooks --source claude"}]}
    out = ms.merge({"model": "opus", "hooks": {"Stop": [other]}}, OURS)
    assert out["model"] == "opus"
    assert commands(out, "Stop")[0] == "flux-hooks --source claude"
    assert len(commands(out, "Stop")) == 2


def test_replaces_old_absolute_path_entries_instead_of_duplicating():
    old = {"matcher": "*", "hooks": [{"type": "command",
           "command": "bash '/srv/old/.claude/hooks/tmux-agent-state.sh' done", "timeout": 5}]}
    out = ms.merge({"hooks": {"Stop": [old]}}, OURS)
    assert commands(out, "Stop") == ['bash "$HOME/.claude/hooks/tmux-agent-state.sh" done']


def test_is_idempotent():
    once = ms.merge({}, OURS)
    assert ms.merge(json.loads(json.dumps(once)), OURS) == once


def test_cli_writes_file_and_backup():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "settings.json")
    json.dump({"theme": "dark"}, open(path, "w"))
    subprocess.run([sys.executable, os.path.join(HERE, "merge_settings.py"), path], check=True)
    out = json.load(open(path))
    assert out["theme"] == "dark" and "SessionStart" in out["hooks"]
    assert any(f.startswith("settings.json.bak-") for f in os.listdir(d))


def test_cli_creates_missing_file():
    path = os.path.join(tempfile.mkdtemp(), "nested", "settings.json")
    subprocess.run([sys.executable, os.path.join(HERE, "merge_settings.py"), path], check=True)
    assert "Stop" in json.load(open(path))["hooks"]
