# Ghostty Configuration

## Overview

Custom Ghostty terminal config built on top of [Omarchy](https://omarchy.org/) defaults.

## Files

| File | Purpose |
|------|---------|
| `config` | Main Ghostty config |
| `shaders/` | Custom GLSL shaders (9 included) |
| `~/.config/omarchy/current/theme/ghostty.conf` | Omarchy theme colors (auto-sourced) |

## Key Settings

### Font
- **Family:** JetBrainsMono Nerd Font
- **Size:** 11 (omarchy default: 9)

### Transparency
- **Opacity:** 0.85
- **Blur:** enabled

### Cursor
- Block style, no blink
- Cursor styling delegated to shell via `shell-integration-features = no-cursor,ssh-env`

### Mouse
- Scroll multiplier: 3 (omarchy default: 0.95)

### Keybindings

| Binding | Action |
|---------|--------|
| `Shift+Insert` | Paste from clipboard |
| `Ctrl+Insert` | Copy to clipboard |
| `Super+Ctrl+Shift+Alt+Arrow` | Resize split (100px) |

## Shaders

Available in `shaders/` — enable by uncommenting in config:

```
custom-shader = shaders/<name>.glsl
custom-shader-animation = true
```

| Shader | Description |
|--------|-------------|
| `aurora.glsl` | Northern lights effect |
| `crt.glsl` | CRT monitor scanlines |
| `cyberpunk-grid.glsl` | Retro grid overlay |
| `lofi-rain.glsl` | Rain droplet effect |
| `matrix.glsl` | Matrix code rain |
| `neon-speed.glsl` | Neon speed lines |
| `plasma.glsl` | Plasma color shift |
| `starfield.glsl` | Star parallax |
| `water.glsl` | Water ripple (GPU-heavy, may cause nvidia issues) |

## Theme

Colors are loaded from the omarchy theme system via:

```
config-file = ?"~/.config/omarchy/current/theme/ghostty.conf"
```

The `?` prefix makes it optional — Ghostty won't error if the file is missing.

Current theme palette: dark background (#121212) with red/amber accents.

## Notes

- `command=~/temp/ghostty-tmux.sh` launches tmux on open — this script must exist on the machine.
- To reset to omarchy defaults: `omarchy-refresh-config ghostty/config`
