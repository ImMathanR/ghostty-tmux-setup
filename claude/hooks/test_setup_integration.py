"""Portable launch paths used by the installer and optional Rex integration."""
import os
from pathlib import Path
import re


HERE = Path(__file__).parent


def test_resurrect_strategy_resolves_from_installed_plugin(tmp_path):
    home = tmp_path / "home"
    strategies = home / ".tmux/plugins/tmux-resurrect/save_command_strategies"
    config = (HERE / "claude-agent.tmux.conf").read_text()
    strategy = re.search(r"set -g @resurrect-save-command-strategy '([^']+)'", config)[1]
    resolved = Path(os.path.normpath(strategies / (strategy + ".sh")))
    assert resolved == home / ".claude/hooks/resurrect-save-command.sh"
    assert os.access(HERE / "resurrect-save-command.sh", os.X_OK)


def test_installer_can_disable_the_startup_painter():
    config = (HERE / "claude-agent.tmux.conf").read_text()
    startup = next(line for line in config.splitlines() if line.startswith("run-shell -b"))
    assert "AGENT_NO_PAINTER" in startup


def test_rex_layer_uses_configurable_python_from_path():
    source = (HERE / "rex-cat-layer.lua").read_text()
    assert 'os.getenv("REX_CAT_PYTHON")' in source
    assert 'or "python3"' in source
    assert "/opt/homebrew/" not in source


def test_smoke_waits_for_hook_work_before_asserting_state():
    smoke = (HERE.parents[1] / "tests/smoke.sh").read_text()
    hook = next(line for line in smoke.splitlines() if line.startswith("hook()"))
    assert "AGENT_STATE_FG=1" in hook
