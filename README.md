# ghostty-tmux-setup

My terminal setup: Ghostty runs tmux, Cmd shortcuts drive tmux, and Claude
Code sessions report their state on their tmux tabs with animated badges and
cat stickers.

## Install

```sh
git clone https://github.com/ImMathanR/ghostty-tmux-setup.git
cd ghostty-tmux-setup
./install.sh
```

`install.sh` does the following. You can run it again at any time:

1.  Installs the dependencies. On macOS it uses Homebrew, and installs
    Homebrew first if it's missing. On Linux it uses apt, dnf or pacman.
    -   CLI tools: `git`, `tmux`, `jq`, `fzf`, `lazygit`, `python3`.
    -   Pillow for Python. The cat stickers are drawn with it.
    -   Ghostty, JetBrainsMono Nerd Font and JetBrains Mono. On Linux, install
        Ghostty yourself from [ghostty.org](https://ghostty.org/docs/install/binary).
2.  Symlinks the configs from this repo into place. If a file is already
    there, it's first renamed to `<file>.bak-<timestamp>`.
3.  Clones the tmux plugins: tpm, tmux-resurrect and tmux-continuum.
4.  Adds the agent hooks to `~/.claude/settings.json`. Your other hooks and
    settings stay as they are.
5.  Checks the result: tools on `PATH`, Pillow, plugins, the tmux config
    (loaded in a private tmux server), the hooks, and the Ghostty config.

| Option        | Effect                                        |
| ------------- | --------------------------------------------- |
| `--skip-deps` | Link the configs and check; install nothing.  |
| `--check`     | Only run the checks.                          |
| `--copy`      | Copy the files instead of symlinking them.    |

After installing, open Ghostty. It attaches to the tmux session `main`, or
creates it. To reload a tmux server that's already running, run
`tmux source-file ~/.tmux.conf`.

## What goes where

| Repo path                   | Installed to                          |
| --------------------------- | ------------------------------------- |
| `ghostty/config`            | `~/.config/ghostty/config`            |
| `ghostty/ide-keys`          | `~/.config/ghostty/ide-keys`          |
| `ghostty/shaders/*`         | `~/.config/ghostty/shaders/`          |
| `tmux/tmux.conf`            | `~/.tmux.conf`                        |
| `bin/ghostty-tmux`          | `~/.local/bin/ghostty-tmux`           |
| `bin/claude-restart`        | `~/.local/bin/claude-restart`         |
| `claude/hooks/*`            | `~/.claude/hooks/`                    |
| `claude/settings.hooks.json`| merged into `~/.claude/settings.json` |

On macOS, Ghostty also reads
`~/Library/Application Support/com.mitchellh.ghostty/config`, which overrides
`~/.config/ghostty/config`. The installer renames that file if it exists.

No file contains a path to a particular home directory. Ghostty expands
`~` in `command`, and resolves the shader path relative to the config file.
`tests/check-paths.sh` enforces this.

## Ghostty

-   Theme: Matte Black (`#121212` background, amber `#FFC107` accents) at 85%
    opacity, JetBrainsMono Nerd Font 14, block cursor.
-   Cursor trail: `shaders/amber-warp.glsl`, an amber version of `cursor_warp`
    from [sahaj-b/ghostty-cursor-shaders](https://github.com/sahaj-b/ghostty-cursor-shaders).
    The other shaders in `ghostty/shaders/` are off. To try one, change
    `custom-shader` in `ghostty/config`.
-   `command = shell:~/.local/bin/ghostty-tmux`. The launcher puts Homebrew on
    `PATH`, because Ghostty starts with the minimal launchd `PATH`.
-   `ghostty/ide-keys` holds the neovim and Android Studio style shortcuts
    (Cmd+O, Cmd+B, Cmd+Alt+L and so on). They're meant for the TAS nvim
    config. To turn them off, delete the `config-file = ?ide-keys` line.

### Keys

Ghostty sends `Ctrl+a` (the tmux prefix) plus a key, so these work in every
pane.

| Keys                        | Action                                 |
| --------------------------- | -------------------------------------- |
| Cmd+T                       | New tab (tmux window)                  |
| Cmd+1 … Cmd+9               | Go to tab 1–9                          |
| Cmd+Shift+[ / Cmd+Shift+]   | Previous / next tab                    |
| Cmd+D / Cmd+Shift+D         | Split right / split down               |
| Cmd+Arrow                   | Move between panes                     |
| Cmd+W / Cmd+Ctrl+W          | Close pane / close tab                 |
| Cmd+Shift+Enter             | Zoom pane                              |
| Cmd+K                       | Clear screen and scrollback            |
| Cmd+F / Cmd+Shift+F         | Search scrollback / copy mode          |
| Cmd+L                       | lazygit popup                          |
| Cmd+J                       | Peek at every Claude tab, most urgent first |
| Cmd+Shift+R                 | Rename tab                             |
| Cmd+Shift+Q                 | Detach (the session keeps running)     |
| Cmd+Ctrl+R                  | Reload the tmux config                 |

## tmux

-   Prefix `Ctrl+a`, mouse on, windows numbered from 1, vi copy mode, 50,000
    lines of history.
-   Status bar: Gruvbox Dark with a gold accent.
-   Sessions are saved every 5 minutes and restored when tmux starts
    (tmux-resurrect and tmux-continuum).
-   Put machine-specific settings in `~/.tmux.local.conf`. If TAS is
    installed, its bindings load from `~/.config/tas/tas-keys.conf`.

## Claude Code agent tabs

The hooks in `claude/hooks/` show what each Claude Code session is doing on
its tmux tab:

| State     | Tab                                                     | Sticker cats       |
| --------- | ------------------------------------------------------- | ------------------ |
| `working` | A light sweeps through the name.                        | `cats/working/`    |
| `ask`     | Breathes pink until you answer. Pleads after 2 minutes. | `cats/ask/`, `cats/ask_long/` |
| `done`    | Mint fills in, blooms, then cools over 10 minutes.      | `cats/done/`, `cats/cold/` |
| `failed`  | A shrug, then the name cracks with a red pen circle.    | `cats/failed/`     |

-   **Stickers**: a cat GIF pops up in the top-right corner of the Ghostty
    window when a tab changes state. It's drawn with the kitty graphics
    protocol through tmux passthrough, so it never takes focus. A tab left
    waiting for 5 minutes gets a `cats/pee/` cat.
-   **Scoreboard**: the right side of the status bar counts the agents in
    each state. Click ▦ to open birdseye, a live card for every tab.
-   **Peek**: Cmd+J opens an fzf list of the Claude tabs with a preview.
-   **Crash restore**: the hooks record which conversation runs in which pane.
    After a crash, tmux-resurrect reopens each pane with
    `claude --resume <id>`.
-   **Prompt colors**: each new interactive session gets a random `/color`
    (`random-color.sh`).
-   **`claude-restart`**: after a Claude Code update, restarts every session
    in tmux on the new version, each in the same conversation. Run
    `claude-restart --dry-run` to see the plan.

Looking at a finished tab clears its badge.

## Tests

```sh
tests/run.sh
```

This runs three checks:

-   `tests/check-paths.sh`: no file names a personal home directory or user.
-   The Python unit tests for the hooks and the settings merge.
-   `tests/smoke.sh`: installs into a temporary `HOME`, then drives a
    sandboxed tmux server. It checks that the plugins load, that every key
    Ghostty sends has a tmux binding, that hook events paint the tab, that the
    launcher attaches, and that a sticker renders. Your running tmux is not
    touched.

## Credits

-   Cursor shaders: [sahaj-b/ghostty-cursor-shaders](https://github.com/sahaj-b/ghostty-cursor-shaders),
    MIT (`ghostty/shaders/LICENSE.cursor-shaders`).
-   The cat GIFs are popular internet memes. Their rights stay with their
    creators.
-   `legacy/omarchy/` is the earlier Omarchy/Hyprland version of this setup,
    kept for reference.
