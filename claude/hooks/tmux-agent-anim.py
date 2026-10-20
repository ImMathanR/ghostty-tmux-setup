#!/usr/bin/env python3
"""Paints animated tmux tab titles for windows whose @agent is set.

Only colour changes, never width: each frame is written to the window option
@agent_fmt, which claude-agent.conf renders in place of " #I:#W ".
  working  a light sweeps through the name (amber on the current tab)
  ask      the tab breathes pink until you answer
  done     mint fills the name letter by letter, each letter flaring as it
           lands, then the tab blooms once and rests in mint with a slow glint
  failed   the tab shrugs, glitches like a dropped signal, then settles in
           rose over a red error squiggle, twitching until your next prompt
Waiting gets personal: an unanswered ask breathes faster and hotter and the
name starts pleading; an unseen done slowly goes cold.
Every state change eases per letter from whatever was on screen, including
the fade back to a plain tab once @agent is cleared.
After 15 quiet minutes (no agent events, no typing) plain tabs doze: they
breathe in a slow wave and z's drift across the scoreboard until anything
happens. Stickers and achievements are fired from here too.
Started on demand by tmux-agent-state.sh; runs for the life of the tmux server.
Demo a late stage: tmux set -w @agent_demo_age 130 before setting @agent.
"""
import fcntl
import math
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_extras as extras  # noqa: E402

SLEEP_AFTER = 900  # quiet seconds before the tabs doze off
# Every frame redraws the status bar, so Ghostty and the macOS compositor redraw
# the (translucent) window too. Steady loops run slowly; only short state
# changes get the smooth rate.
TRANSITION_FPS, STEADY_FPS, SLEEP_FPS = 30, 8, 2
STICKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmux-agent-sticker.py")
CRACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmux-agent-crack.py")
WORKING_STICKER_EVERY = 60  # the working cat is fun once a minute, not every prompt
STUCK_AFTER = 300           # ask -> crying cat
GHOSTED_AFTER, MARATHON_AFTER = 1200, 1800

# "a+", not "w": opening with "w" empties the file before we know whether we get
# the lock, wiping the running painter's pid that the hook checks
lock = open(os.path.expanduser("~/.claude/hooks/.tmux-agent-anim.lock"), "a+")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    raise SystemExit(0)  # another painter is running
lock.seek(0)
lock.truncate()
lock.write(str(os.getpid()))  # lets the hook check "running?" without launching Python
lock.flush()


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


BAR = hexrgb("#1a1a1a")  # status-style bg
IDLE, CURRENT = hexrgb("#8a8a8d"), hexrgb("#FFC107")
GREY, GREY_HI = hexrgb("#6a6a6e"), hexrgb("#f2f2f2")
AMBER_HI = hexrgb("#fff3c4")
PINK, PINK_DEEP, INK = hexrgb("#ff7eb6"), hexrgb("#c2407e"), hexrgb("#1a1a1a")
MINT, MINT_HI, MINT_BLOOM = hexrgb("#5fd7a7"), hexrgb("#eafff5"), hexrgb("#1f5a45")
ROSE, SQUIGGLE, SQUIGGLE_HI = hexrgb("#d9a8a0"), hexrgb("#ff5a36"), hexrgb("#ffc2ad")
TEAR_RED, TEAR_CYAN, EMBER = hexrgb("#ff4a3d"), hexrgb("#5ad1ff"), hexrgb("#3d1511")
GLYPHS = "▚▞▖▗▘▝░▒"
SLEEPY, ZZZ_LO, ZZZ_HI = hexrgb("#4a4a4e"), hexrgb("#4a4a50"), hexrgb("#a0a0a8")

# done choreography (seconds)
FILL_SPAN = 0.55    # delay between first and last letter starting
FILL_LETTER = 0.36  # each letter's own ease
FILL_CURVE = 1.7    # >1: letters start quickly, then the front decelerates
BLOOM_AT = FILL_SPAN + FILL_LETTER * 0.55  # overlaps the last letter's flare
BLOOM_RISE, BLOOM = 0.09, 0.75             # quick swell, then a long exhale
GLINT_EVERY, GLINT_LEN = 8.0, 1.2
# failed choreography
GLITCH = 0.42                      # scramble decays over this long
SQUIGGLE_AT, SQUIGGLE_SPAN, SQUIGGLE_LETTER = 0.28, 0.35, 0.18
TIC_EVERY, TIC_LEN = 6.0, 0.12     # resting twitch
SHRUG = 0.6                        # shrug holds this long before the glitch
SHRUGS = ["¯\\_(ツ)_/¯", "¯\\(ツ)/¯", "(ツ)"]
WIDE = {"ツ"}                      # glyphs that take two cells
# ask escalation: the guilt trip
GUILT_AFTER, GUILT_FULL = 60, 300  # breathing speeds up from 1 min, maxes at 5
PLEA_AFTER, PLEA_EVERY, PLEA_LEN = 120, 12.0, 1.8
PLEAS = [(120, ["hello??", "u there", "psst", "hi?"]),
         (300, ["*taps glass*", "still here", "helloooo", "pls"]),
         (600, ["i'll wait", "it's fine.", "no rush.", "sigh"])]
PINK_HOT, PINK_HOT_DEEP = hexrgb("#ff4f7a"), hexrgb("#b8203f")
# done cooling: food going cold
COLD_AFTER = 600
MINT_COLD = hexrgb("#7d9a8f")
# every other state change
SHIFT_SPAN, SHIFT_LETTER = 0.18, 0.28


# ── easing ──
def clamp(t):
    return max(0.0, min(1.0, t))


def out_cubic(t):
    return 1 - (1 - clamp(t)) ** 3


def in_out_sine(t):
    return -(math.cos(math.pi * clamp(t)) - 1) / 2


def mix(a, b, t):
    t = clamp(t)
    return tuple(x + (y - x) * t for x, y in zip(a, b))


# ── cells: (fg, bg, bold, underline colour or None, glyph or None) per character ──
def plain(text, active):
    return [(CURRENT if active else IDLE, BAR, active, None, None)] * len(text)


def noise(*key):
    return random.Random(hash(key))


def torn(rng):
    return (TEAR_RED if rng.random() < 0.6 else TEAR_CYAN), rng.choice(GLYPHS)


def gaussian(i, head, width):
    return math.exp(-((i - head) ** 2) / (2 * width ** 2))


def cells_of(word):
    """Glyph per terminal cell: a wide glyph fills its cell and blanks the next."""
    out = []
    for ch in word:
        out += [ch, ""] if ch in WIDE else [ch]
    return out


def flip(glyphs, start, word, q, dur):
    """Split-flap swap of glyphs[start:] to word for dur seconds (q = time in)."""
    out = list(glyphs)
    word = cells_of(word)
    for k in range(len(glyphs) - start):
        i, t_in, t_out = start + k, k * 0.025, dur - 0.3 + k * 0.025
        if abs(q - t_in) < 0.03 or abs(q - t_out) < 0.03:
            out[i] = "▚"
        elif t_in <= q < t_out:
            out[i] = word[k] if k < len(word) else " "
    return out


def plea_for(text, waited, cycle):
    name_start = text.index(":") + 1
    room = len(text) - 1 - name_start
    level = [words for after, words in PLEAS if waited >= after][-1]
    fits = [w for w in level if len(cells_of(w)) <= room] or \
           [w for _, words in PLEAS for w in words if len(cells_of(w)) <= room]
    return name_start, (noise("plea", cycle).choice(fits) if fits else None)


def shrug_for(text):
    for s in SHRUGS:
        if len(cells_of(s)) <= len(text):
            pad = len(text) - len(cells_of(s))
            return [" "] * (pad // 2) + cells_of(s) + [" "] * (pad - pad // 2)
    return None


def target(state, text, active, now, rest_age):
    n = len(text)
    if state == "working":
        # the selected tab keeps full amber; the sweep only brightens it
        lo, hi = (CURRENT, AMBER_HI) if active else (GREY, GREY_HI)
        head = (now * 6) % (n + 10) - 5  # under a cell per frame at STEADY_FPS: the glow glides
        return [(mix(lo, hi, gaussian(i, head, 1.5)), BAR, active, None, None) for i in range(n)]
    if state == "ask":
        waited = max(0.0, rest_age)
        heat = in_out_sine((waited - GUILT_AFTER) / (GUILT_FULL - GUILT_AFTER))
        period = 2.0 - 0.8 * heat  # slow enough to stay smooth at STEADY_FPS
        k = (math.sin(waited * 2 * math.pi / period) + 1) / 2
        bg = mix(mix(PINK_DEEP, PINK_HOT_DEEP, heat), mix(PINK, PINK_HOT, heat), k)
        glyphs = [None] * n
        if waited >= PLEA_AFTER:
            cycle, q = divmod(waited - PLEA_AFTER, PLEA_EVERY)
            start, word = plea_for(text, waited, int(cycle))
            if word and q < PLEA_LEN:
                glyphs = flip(glyphs, start, word, q, PLEA_LEN)
                glyphs[-1] = None  # keep the trailing pad
        return [(INK, bg, True, None, g) for g in glyphs]
    if state == "done":
        # first glint waits a full cycle so it never crowds the bloom
        q = (rest_age % GLINT_EVERY) / GLINT_LEN if rest_age >= GLINT_EVERY else 2
        cold = in_out_sine(rest_age / COLD_AFTER) if rest_age > 0 else 0
        base = mix(MINT, MINT_COLD, cold)
        if q >= 1:
            return [(base, BAR, False, None, None)] * n
        head = in_out_sine(q) * (n + 4) - 2
        return [(mix(base, MINT_HI, 0.5 * (1 - cold) * gaussian(i, head, 1.2)), BAR, False, None, None)
                for i in range(n)]
    if state == "failed":
        fg = CURRENT if active else ROSE  # selection stays readable; the squiggle carries the error
        cells = [(fg, BAR, active, None if text_char_is_space(i, n) else SQUIGGLE, None)
                 for i in range(n)]
        cycle = int(rest_age // TIC_EVERY)
        if rest_age >= TIC_EVERY and rest_age % TIC_EVERY < TIC_LEN:
            rng = noise("tic", cycle)
            for i in rng.sample(range(1, n - 1), min(2, n - 2)):
                fg, glyph = torn(rng)
                cells[i] = (fg, BAR, False, SQUIGGLE, glyph)
        return cells
    if state == "sleep":
        if active:  # the selected tab never dims
            return plain(text, True)
        lag = int(text.split(":")[0]) * 0.7  # a slow wave across the tabs
        k = (math.sin(now * 2 * math.pi / 5.0 - lag) + 1) / 2
        return [(mix(SLEEPY, IDLE, k), BAR, False, None, None)] * n
    return plain(text, active)


def letter_progress(i, n, age, span, letter, curve=1.0):
    start = span * (i / max(1, n - 1)) ** curve
    return clamp((age - start) / letter)


def blend(prev, goal, i, n, age, arriving, text=""):
    fg0, bg0, _, ul0, _ = prev[i] if i < len(prev) else goal[i]
    fg1, bg1, bold1, ul1, glyph1 = goal[i]
    if arriving == "failed" and age < SHRUG:
        shrug = shrug_for(text)
        glyphs = flip([None] * n, 0, "".join(g for g in shrug if g) if shrug else "", age, SHRUG + 1)
        if shrug:  # flip() writes words char by char; restore exact cells incl. wide blanks
            glyphs = [g if g in (None, "▚") else shrug[j] for j, g in enumerate(glyphs)]
        return mix(fg0, ROSE, out_cubic(age / 0.2)), BAR, True, None, glyphs[i]
    if arriving == "failed":
        age -= SHRUG
        g = 1 - out_cubic(age / GLITCH)
        frame = int(age * 30)
        rng = noise("glitch", frame, i)
        flicker = g * (noise("flicker", frame).random() < 0.4)
        bg = mix(BAR, EMBER, flicker)
        q = letter_progress(i, n, age - SQUIGGLE_AT, SQUIGGLE_SPAN, SQUIGGLE_LETTER)
        ul = mix(SQUIGGLE_HI, SQUIGGLE, out_cubic(q)) if q > 0 and ul1 else None
        if text_char_is_space(i, n) or rng.random() >= 0.9 * g:
            return mix(fg0, fg1, out_cubic(age / GLITCH)), bg, bold1, ul, None
        fg, glyph = torn(rng)
        return fg, bg, bold1, ul, glyph
    if arriving == "done":
        p = letter_progress(i, n, age, FILL_SPAN, FILL_LETTER, FILL_CURVE)
        fg = mix(fg0, fg1, out_cubic(p))
        fg = mix(fg, MINT_HI, 0.85 * math.sin(math.pi * p))  # flare as it lands
        landed = age - BLOOM_AT
        bloom = out_cubic(landed / BLOOM_RISE) * (1 - clamp((landed - BLOOM_RISE) / BLOOM)) ** 2.2 \
            if landed >= 0 else 0
        bg = mix(mix(bg0, bg1, out_cubic(p)), MINT_BLOOM, bloom)
        return fg, bg, bold1, None, None
    p = letter_progress(i, n, age, SHIFT_SPAN, SHIFT_LETTER)
    e = out_cubic(p)
    # the squiggle erases (or draws) letter by letter at each letter's midpoint
    return mix(fg0, fg1, e), mix(bg0, bg1, e), bold1, (ul1 if p >= 0.5 else ul0), glyph1


def text_char_is_space(i, n):
    return i == 0 or i == n - 1  # the padding cells stay quiet


def transition_len(state):
    if state == "done":
        return BLOOM_AT + BLOOM_RISE + BLOOM
    if state == "failed":
        return SHRUG + SQUIGGLE_AT + SQUIGGLE_SPAN + SQUIGGLE_LETTER
    return SHIFT_SPAN + SHIFT_LETTER


def encode(text, cells):
    out, last = [], None
    hx = lambda c: "#%02x%02x%02x" % tuple(round(v) for v in c)
    for ch, (fg, bg, bold, ul, glyph) in zip(text, cells):
        # "none" first: status styles accumulate, so each run resets attributes
        style = "#[none,fg=%s,bg=%s%s%s]" % (
            hx(fg),
            "default" if all(abs(a - b) < 1 for a, b in zip(bg, BAR)) else hx(bg),
            ",bold" if bold else "",
            ",curly-underscore,us=" + hx(ul) if ul else "")
        if style != last:
            out.append(style)
            last = style
        ch = ch if glyph is None else glyph
        out.append("##" if ch == "#" else ch)
    return "".join(out)


def tmux(args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout


# ── cat stickers ──
MOOD = {"working": "working", "ask": "ask", "ask+": "pee",
        "done": "done", "done+": "cold", "failed": "failed"}
RANK = {"failed": 3, "ask": 2, "working": 1}
bar = {"cleared": False}
last_working_sticker = [-1e9]
def to_ghostty(seq):
    tty = tmux(["display", "-p", "#{pane_tty}"]).strip()
    if tty:
        try:
            with open(tty, "w") as f:
                f.write("\x1bPtmux;" + seq.replace("\x1b", "\x1b\x1b") + "\x1b\\")
        except OSError:
            pass


tracker = extras.Tracker()
trophies = []  # achievements waiting for a quiet moment to show
last_sticker = [-1e9]


def sticker(*args):
    last_sticker[0] = time.monotonic()
    subprocess.Popen([sys.executable, STICKER, *args], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def react(events, states, now):
    """events: (event, state before, "idx:name", looking at it right now)."""
    best = None
    working = sum(s == "working" for s in states)
    for state, before, label, viewing in sorted(events, key=lambda e: -RANK.get(e[0].rstrip("+"), 0)):
        extras.log(state, label)
        trophies.extend(tracker.observe(state, label, working))
        if state not in MOOD:
            continue  # milestones like ghosted only feed achievements
        if state == "working":
            if before == "ask" or now - last_working_sticker[0] < WORKING_STICKER_EVERY:
                continue  # answering a question isn't a new task
            last_working_sticker[0] = now
        best = best or (MOOD[state], label)
    if best:
        sticker(*best)
    elif trophies and now - last_sticker[0] > 4.5:  # don't talk over a sticker
        title, line = trophies.pop(0)
        sticker("achievement", title, "5", line)
    if not bar["cleared"]:  # the progress bar is retired; hide any left from older runs
        bar["cleared"] = True
        to_ghostty("\x1b]9;4;0\x07")


# ── scoreboard: the status-right summary, clickable per tab ──
def ago(seconds):
    return "%ds" % seconds if seconds < 60 else "%dm" % (seconds // 60)


def zzz(t, width=7):
    """z's drifting left and growing as they float away from the clock."""
    cells = [" "] * width
    for k in range(3):
        x = (t * 0.9 + k * width / 3) % width
        pos = width - 1 - int(x)
        glyph = "Z" if x > width * 0.6 else "z"
        cells[pos] = "#[fg=%s]%s" % ("#%02x%02x%02x" % tuple(round(v) for v in
                                     mix(ZZZ_HI, ZZZ_LO, x / width)), glyph)
    return "".join(c if c != " " else " " for c in cells) + "  "


def scoreboard(entries, snooze=None):
    """entries: (state, index, name, seconds in state). Returns a tmux format string."""
    def link(idx, style, body):
        return "#[range=window|%s]#[none,%s]%s#[norange]" % (idx, style, body.replace("#", "##"))

    def short(name):
        return name if len(name) <= 14 else name[:13] + "…"

    parts = []
    asks = sorted((e for e in entries if e[0] == "ask"), key=lambda e: -e[3])
    if asks:
        _, idx, name, waited = asks[0]
        hot = "fg=#ff4f7a,bold" if waited >= STUCK_AFTER else "fg=#ff7eb6,bold"
        what = "needs you" if waited < 60 else "waiting " + ago(waited)
        extra = " +%d" % (len(asks) - 1) if len(asks) > 1 else ""
        parts.append(link(idx, hot, "%s:%s %s%s" % (idx, short(name), what, extra)))
    fails = sorted((e for e in entries if e[0] == "failed"), key=lambda e: -e[3])
    if fails:
        _, idx, name, _ = fails[0]
        extra = " +%d" % (len(fails) - 1) if len(fails) > 1 else ""
        parts.append(link(idx, "fg=#ff5a36", "%s:%s failed%s" % (idx, short(name), extra)))
    busy = [e for e in entries if e[0] == "working"]
    if busy:
        parts.append(link(busy[0][1], "fg=#8a8a8d", "%d busy" % len(busy)))
    done = sorted((e for e in entries if e[0] == "done"), key=lambda e: -e[3])
    if done:  # clicking goes to the one that has waited longest
        parts.append(link(done[0][1], "fg=#5fd7a7", "%d done" % len(done)))
    lead = zzz(snooze) if snooze is not None else ""
    return lead + "  ".join(parts) + ("  " if parts else "")


MILESTONES = {"ask": [(STUCK_AFTER, "ask+"), (GHOSTED_AFTER, "ghosted")],
              "done": [(COLD_AFTER, "done+")], "working": [(MARATHON_AFTER, "marathon")]}
tabs = {}  # window_id -> dict(state, since, prev, cells)
shown_score = [None]
last_change, client = time.time(), {"checked": 0.0, "activity": 0.0, "focused": False}
while True:
    now = time.monotonic()
    rows = tmux(["list-windows", "-a", "-f", "#{?#{m:_*,#{session_name}},0,1}", "-F",
                 "#{window_id}\t#{window_index}\t#{window_name}\t#{window_active}\t#{@agent}\t#{@agent_fmt}\t#{@agent_demo_age}\t#{@agent_at}"])
    if not rows:
        break  # tmux server gone
    if now - client["checked"] > 1.5:
        seen = [l.split(" ", 1) for l in tmux(["list-clients", "-f", "#{?#{m:_*,#{client_session}},0,1}", "-F", "#{client_activity} #{client_flags}"]).splitlines()]
        # plain tabs use the host config's own colours (tas: gruvbox; as-tmux: grey/amber)
        for opt, name in (("@agent_plain_fmt", "IDLE"), ("@agent_plain_current_fmt", "CURRENT")):
            m = re.search(r"fg=(#[0-9a-fA-F]{6})", tmux(["show", "-gqv", opt]))
            if m:
                globals()[name] = hexrgb(m.group(1))
        client.update(checked=now, activity=max([float(a) for a, _ in seen] or [0]),
                      focused=any("focused" in f for _, f in seen),
                      demo_sleep=tmux(["show", "-gqv", "@agent_demo_sleep"]).strip() == "on")
    real_states = [(l.split("\t") + [""] * 5)[4] for l in rows.splitlines()]
    sleeping = client.get("demo_sleep") or (  # @agent_demo_sleep on: doze right now
        time.time() - max(last_change, client["activity"]) > SLEEP_AFTER
        and not any(st in ("working", "ask") for st in real_states))
    cmds, fps, events, board = [], 2, [], []
    for line in rows.splitlines():
        wid, idx, name, active, real, fmt, demo_age, at = (line.split("\t") + [""] * 8)[:8]
        state = real or ("sleep" if sleeping else "")  # plain tabs doze while it's quiet
        text, active = " %s:%s " % (idx, name), active == "1"
        label, viewing = "%s:%s" % (idx, name), active and client["focused"]
        tab = tabs.get(wid)
        if tab is None:
            if not state:
                if fmt:  # stale frame from a painter that died mid-fade
                    cmds += ["set", "-wu", "-t", wid, "@agent_fmt", ";"]
                continue
            tab = tabs[wid] = {"state": None, "since": now, "prev": plain(text, active), "cells": None, "real": ""}
        if tab["real"] != real:
            tab["real"], last_change = real, time.time()
        if tab["state"] != (state or None):
            fresh = at and time.time() - float(at) < 3
            if fresh and real:
                events.append((real, tab["state"], label, viewing))
            tab["prev"] = tab["cells"] or plain(text, active)
            # @agent_demo_age pretends the state began that many seconds ago (for demos)
            tab["state"], tab["since"] = state or None, now - float(demo_age or 0)
        age = now - tab["since"]
        settle = transition_len(tab["state"])
        if tab["state"] == "failed" and not tab.get("cracked"):
            # the glass breaks as the shrug ends; an old failure just shows up cracked
            when = "%.2f" % max(0, SHRUG - age) if age < SHRUG else "static"
            subprocess.Popen([sys.executable, CRACK, wid, when], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        tab["cracked"] = tab["state"] == "failed"
        for after, milestone in MILESTONES.get(tab["state"], ()):
            if tab.get("last_age", age) < after + settle <= age:
                events.append((milestone, None, label, viewing))
        tab["last_age"] = age
        goal = target(tab["state"], text, active, now, age - settle)
        if age < settle:
            fps = TRANSITION_FPS
            cells = [blend(tab["prev"], goal, i, len(text), age, tab["state"], text)
                     for i in range(len(text))]
        else:
            cells = goal
            if tab["state"] is None:  # faded back to a plain tab
                del tabs[wid]
                cmds += ["set", "-wu", "-t", wid, "@agent_fmt", ";"]
                continue
            rest = age - settle
            if tab["state"] in ("working", "ask") or \
                    (tab["state"] == "done" and rest >= GLINT_EVERY and rest % GLINT_EVERY < GLINT_LEN) or \
                    (tab["state"] == "failed" and rest >= TIC_EVERY and rest % TIC_EVERY < TIC_LEN + 0.1):
                fps = max(fps, STEADY_FPS)
            elif tab["state"] == "sleep":
                fps = max(fps, SLEEP_FPS)
        if tab["state"] == "failed" and age >= SHRUG + 0.5:
            # the crack overlay's red pen takes over; a squiggle would peek out below it
            cells = [(fg, bg, bold, None, glyph) for fg, bg, bold, _, glyph in cells]
        tab["cells"] = cells
        if tab["state"] and tab["state"] != "sleep":
            board.append((tab["state"], idx, name, int(max(0, age - settle))))
        frame = encode(text, cells)
        if frame != fmt:
            cmds += ["set", "-w", "-t", wid, "@agent_fmt", frame, ";"]
    for wid in set(tabs) - {l.split("\t", 1)[0] for l in rows.splitlines()}:
        del tabs[wid]  # window closed
    if cmds:
        tmux(cmds[:-1])
    react(events, [t["state"] for t in tabs.values()], now)
    score = scoreboard(board, now if sleeping else None)
    if score != shown_score[0]:
        shown_score[0] = score
        tmux(["set", "-g", "@agent_score", score])
    time.sleep(1 / fps)
