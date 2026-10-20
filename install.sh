#!/usr/bin/env bash
# Installs Ghostty + tmux + the Claude Code agent tabs from this repo.
#
#   ./install.sh              install dependencies, link configs, verify
#   ./install.sh --skip-deps  only link configs and verify
#   ./install.sh --check      only verify an existing install
#   ./install.sh --copy       copy files instead of symlinking them
#
# Safe to run again: it skips what is already in place, and any file it would
# replace is first moved aside as <file>.bak-<timestamp>.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date +%Y%m%d%H%M%S)"
OS="$(uname -s)"
DEPS=1 LINK=1 MODE=link

for arg in "$@"; do
  case "$arg" in
    --skip-deps) DEPS=0 ;;
    --check) DEPS=0 LINK=0 ;;
    --copy) MODE=copy ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then B=$'\e[1m' G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' N=$'\e[0m'; else B='' G='' Y='' R='' N=''; fi
step() { printf '\n%s==> %s%s\n' "$B" "$*" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '%sERROR:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Homebrew may be installed but not on PATH (e.g. launched from a GUI app).
load_brew() {
  local b
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
    if [ -x "$b" ]; then eval "$("$b" shellenv)"; return 0; fi
  done
  return 1
}

# ── Dependencies ────────────────────────────────────────────────────────────
FORMULAE=(git tmux jq fzf lazygit python)   # brew names
CASKS=(ghostty font-jetbrains-mono-nerd-font font-jetbrains-mono)

pillow_ok() { python3 -c 'import PIL' >/dev/null 2>&1; }

install_pillow() {
  pillow_ok && { ok "Pillow (Python imaging, draws the cat stickers)"; return; }
  if have brew && [ "$(command -v python3)" = "$(brew --prefix)/bin/python3" ]; then
    brew install pillow >/dev/null || true
  fi
  pillow_ok || python3 -m pip install --user --quiet Pillow 2>/dev/null \
    || python3 -m pip install --user --quiet --break-system-packages Pillow
  pillow_ok && ok "Pillow installed" || die "could not install Pillow for $(command -v python3)"
}

deps_macos() {
  if ! load_brew; then
    step "Installing Homebrew"
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    load_brew || die "Homebrew installed but brew is not on PATH"
  fi
  ok "Homebrew $(brew --version | head -1 | awk '{print $2}')"

  local f missing=()
  for f in "${FORMULAE[@]}"; do
    case "$f" in python) have python3 && [ "$(command -v python3)" != /usr/bin/python3 ] && continue ;;
                 *) have "$f" && continue ;; esac
    missing+=("$f")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "  installing: ${missing[*]}"
    brew install "${missing[@]}"
  fi
  ok "CLI tools: ${FORMULAE[*]}"

  local c installed
  installed="$(brew list --cask -1 2>/dev/null || true)"
  missing=()
  for c in "${CASKS[@]}"; do
    grep -qx "$c" <<<"$installed" && continue
    [ "$c" = ghostty ] && [ -d /Applications/Ghostty.app ] && continue
    missing+=("$c")
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "  installing: ${missing[*]}"
    brew install --cask "${missing[@]}"
  fi
  ok "Ghostty and JetBrains Mono fonts"
}

deps_linux() {
  local pkgs
  if have apt-get; then
    pkgs=(git tmux jq fzf python3 python3-pil curl xz-utils fontconfig)
    sudo apt-get update -qq && sudo apt-get install -y -qq "${pkgs[@]}"
  elif have dnf; then
    pkgs=(git tmux jq fzf python3 python3-pillow curl xz fontconfig)
    sudo dnf install -y -q "${pkgs[@]}"
  elif have pacman; then
    pkgs=(git tmux jq fzf python python-pillow lazygit ghostty curl xz fontconfig)
    sudo pacman -S --needed --noconfirm "${pkgs[@]}"
  elif load_brew; then
    brew install "${FORMULAE[@]}"
  else
    die "no supported package manager (apt-get, dnf, pacman or Homebrew)"
  fi
  ok "CLI tools"

  if ! have lazygit; then
    if load_brew; then brew install lazygit
    else
      local arch v
      arch="$(uname -m)"; [ "$arch" = aarch64 ] && arch=arm64
      v="$(curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')"
      mkdir -p "$HOME/.local/bin"
      curl -fsSL "https://github.com/jesseduffield/lazygit/releases/download/v${v}/lazygit_${v}_Linux_${arch}.tar.gz" \
        | tar -xz -C "$HOME/.local/bin" lazygit
    fi
  fi
  have lazygit || [ -x "$HOME/.local/bin/lazygit" ] && ok "lazygit"

  local fonts="$HOME/.local/share/fonts"
  if ! ls "$fonts"/JetBrainsMonoNerdFont-Regular.ttf >/dev/null 2>&1; then
    mkdir -p "$fonts"
    curl -fsSL https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz \
      | tar -xJ -C "$fonts" && { fc-cache -f "$fonts" >/dev/null 2>&1 || true; }
  fi
  ok "JetBrainsMono Nerd Font"
  have ghostty || warn "install Ghostty from https://ghostty.org/docs/install/binary (no apt/dnf package)"
}

# ── Linking ─────────────────────────────────────────────────────────────────
# put <repo file> <destination>: symlink (or copy) it, moving aside anything else there.
put() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ "$MODE" = link ] && [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then return; fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    if [ "$MODE" = copy ] && [ ! -L "$dst" ] && diff -rq "$src" "$dst" >/dev/null 2>&1; then return; fi
    mv "$dst" "$dst.bak-$STAMP"
    warn "moved aside ${dst/#$HOME/~} → $(basename "$dst").bak-$STAMP"
  fi
  if [ "$MODE" = link ]; then ln -s "$src" "$dst"; else cp -R "$src" "$dst"; fi
}

link_ghostty() {
  local dir="${XDG_CONFIG_HOME:-$HOME/.config}/ghostty" f
  # Ghostty also reads these; a leftover one would override ours.
  local others=("$dir/config.ghostty")
  [ "$OS" = Darwin ] && others+=("$HOME/Library/Application Support/com.mitchellh.ghostty/config"
                                 "$HOME/Library/Application Support/com.mitchellh.ghostty/config.ghostty")
  for f in "${others[@]}"; do
    if [ -e "$f" ] || [ -L "$f" ]; then
      mv "$f" "$f.bak-$STAMP"
      warn "moved aside ${f/#$HOME/~} (it would override the repo config)"
    fi
  done
  put "$REPO/ghostty/config" "$dir/config"
  put "$REPO/ghostty/ide-keys" "$dir/ide-keys"
  for f in "$REPO"/ghostty/shaders/*; do put "$f" "$dir/shaders/$(basename "$f")"; done
  ok "Ghostty → ${dir/#$HOME/~}"
}

link_tmux() {
  put "$REPO/tmux/tmux.conf" "$HOME/.tmux.conf"
  put "$REPO/bin/ghostty-tmux" "$HOME/.local/bin/ghostty-tmux"
  put "$REPO/bin/claude-restart" "$HOME/.local/bin/claude-restart"
  ok "tmux → ~/.tmux.conf, ghostty-tmux and claude-restart → ~/.local/bin"

  local p name
  for p in tmux-plugins/tpm tmux-plugins/tmux-resurrect tmux-plugins/tmux-continuum; do
    name="${p#*/}"
    if [ -d "$HOME/.tmux/plugins/$name/.git" ]; then
      git -C "$HOME/.tmux/plugins/$name" pull -q --ff-only 2>/dev/null || true
    else
      rm -rf "$HOME/.tmux/plugins/$name"
      git clone -q --depth 1 "https://github.com/$p" "$HOME/.tmux/plugins/$name"
    fi
  done
  ok "tmux plugins: tpm, tmux-resurrect, tmux-continuum"
}

link_claude() {
  local hooks="$HOME/.claude/hooks" f
  # Link each item, not the folder, so other hooks in ~/.claude/hooks stay.
  # The scripts keep their runtime state next to themselves, in ~/.claude/hooks.
  for f in "$REPO"/claude/hooks/*; do
    [ "$(basename "$f")" = __pycache__ ] && continue
    put "$f" "$hooks/$(basename "$f")"
  done
  python3 "$REPO/claude/merge_settings.py" "$HOME/.claude/settings.json"
  ok "Claude Code hooks → ~/.claude/hooks, wired into ~/.claude/settings.json"
}

# ── Verification ────────────────────────────────────────────────────────────
FAILS=0
check() {  # check <label> <command...>
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$label"; else printf '  %s✗%s %s\n' "$R" "$N" "$label"; FAILS=$((FAILS + 1)); fi
}

tmux_conf_loads() {
  # A private tmux server on a throwaway socket, so a running session is
  # untouched. tpm is left out: continuum would restore saved sessions into it.
  # AGENT_NO_PAINTER: a tab painter started here could still hold its lock
  # when the first real Claude hook runs, which would then not start one.
  local sock="gts-check-$$" conf out agent
  conf="$(mktemp)"
  grep -v 'plugins/tpm/tpm' "$HOME/.tmux.conf" >"$conf"
  out="$(AGENT_NO_PAINTER=1 tmux -L "$sock" -f "$conf" new-session -d -s check \; show -gv prefix 2>&1)"
  agent="$(tmux -L "$sock" show -gv window-status-format 2>/dev/null)"
  tmux -L "$sock" kill-server 2>/dev/null || true
  rm -f "$conf"
  [ "$out" = C-a ] && [[ "$agent" == *@agent_fmt* ]]
}

hooks_wired() {
  python3 - "$HOME/.claude/settings.json" <<'PY'
import json, sys
h = json.load(open(sys.argv[1]))["hooks"]
need = {"Stop", "Notification", "PreToolUse", "SessionStart", "UserPromptSubmit"}
assert all(any("tmux-agent-state.sh" in x["command"] for g in h[e] for x in g["hooks"]) for e in need)
PY
}

ghostty_bin() {
  if have ghostty; then command -v ghostty
  elif [ -x /Applications/Ghostty.app/Contents/MacOS/ghostty ]; then echo /Applications/Ghostty.app/Contents/MacOS/ghostty
  fi
}

verify() {
  step "Verifying"
  local t
  for t in git tmux jq fzf lazygit python3; do check "$t on PATH" have "$t"; done
  check "Pillow importable by $(command -v python3 || echo python3)" pillow_ok
  check "tmux $(tmux -V 2>/dev/null | awk '{print $2}') is 3.3 or newer (popups, passthrough)" \
    awk -v v="$(tmux -V 2>/dev/null | sed 's/[^0-9.]//g')" 'BEGIN { exit !(v + 0 >= 3.3) }'
  check "tmux plugins present" test -x "$HOME/.tmux/plugins/tpm/tpm" -a -d "$HOME/.tmux/plugins/tmux-resurrect" -a -d "$HOME/.tmux/plugins/tmux-continuum"
  check "~/.tmux.conf loads with agent tabs (private test server)" tmux_conf_loads
  check "launcher ~/.local/bin/ghostty-tmux is executable" test -x "$HOME/.local/bin/ghostty-tmux"
  check "agent hooks in ~/.claude/hooks" test -f "$HOME/.claude/hooks/tmux-agent-state.sh" -a -d "$HOME/.claude/hooks/cats/done"
  check "hooks wired into ~/.claude/settings.json" hooks_wired
  local gb; gb="$(ghostty_bin)"
  if [ -n "$gb" ]; then
    check "Ghostty config is valid" "$gb" +validate-config --config-file="${XDG_CONFIG_HOME:-$HOME/.config}/ghostty/config"
  else
    warn "Ghostty not found, skipped config validation"
  fi
  if [ "$FAILS" -gt 0 ]; then die "$FAILS check(s) failed"; fi
}

# ── Main ────────────────────────────────────────────────────────────────────
load_brew || true
export PATH="$HOME/.local/bin:$PATH"

if [ "$DEPS" = 1 ]; then
  step "Installing dependencies ($OS)"
  case "$OS" in
    Darwin) deps_macos ;;
    Linux) deps_linux ;;
    *) die "unsupported OS: $OS" ;;
  esac
  install_pillow
fi

if [ "$LINK" = 1 ]; then
  have git && have tmux && have python3 || die "git, tmux and python3 are required (run without --skip-deps)"
  step "Linking configs from $REPO"
  link_ghostty
  link_tmux
  link_claude
fi

verify

cat <<EOF

${B}Done.${N} Open Ghostty: it starts tmux in the session "main".
  Reload a running tmux:  tmux source-file ~/.tmux.conf
  Re-run checks later:    $REPO/install.sh --check
EOF
