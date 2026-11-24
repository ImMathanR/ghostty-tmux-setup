#!/usr/bin/env python3
"""Pops a cat sticker in the top-right corner of the Ghostty window.

  tmux-agent-sticker.py <mood> <tab label> [seconds] [caption]
  moods: working ask ask_long done cold failed achievement
  art: a random GIF from cats/<mood>/, never the same one twice in a row;
       falls back to cats/<mood>.gif, then cats/<mood>.png

The card is drawn with the kitty graphics protocol, sent through tmux
passthrough straight to Ghostty, so it floats over whatever is on screen and
never takes focus. A newer sticker replaces an older one. Ghostty has no
image animation, so GIFs are played here: every frame is uploaded once, then
the visible placement is swapped at the GIF's own frame timing.
"""
import base64
import glob
import json
import math
import os
import random
import signal
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont, ImageSequence

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".sticker-cache")
PIDFILE = os.path.join(HERE, ".sticker%s.pid" % ("-" + os.path.basename(os.environ["STICKER_TTY"]) if os.environ.get("STICKER_TTY") else ""))
IMAGE_ID = 4242
COLS = 18  # card width in terminal cells

MOODS = {  # outline/name colour, caption
    "working": ("#d0d0d0", "on it"),
    "ask": ("#ff7eb6", "needs you"),
    "ask_long": ("#ff4f7a", "still waiting on you"),
    "done": ("#5fd7a7", "done"),
    "cold": ("#7d9a8f", "done, getting cold"),
    "failed": ("#ff5a36", "failed"),
    "achievement": ("#ffd54f", "achievement unlocked"),
    "pee": ("#e8c547", "ignored for 5 minutes, so..."),
}
FALLBACK = {"achievement": "done", "pee": "ask_long"}  # borrow a celebrating cat until it has its own pool
CARD, CAPTION_GREY = "#1e1e1e", "#9a9a9e"


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout.strip()


def font(weight, size):
    for d in (os.path.expanduser("~/Library/Fonts"), "/Library/Fonts"):
        hits = glob.glob(os.path.join(d, "JetBrainsMono-%s.ttf" % weight))
        if hits:
            return ImageFont.truetype(hits[0], size)
    return ImageFont.load_default()


def pick(mood):
    """A random file from the mood's pool, avoiding whatever it showed last time."""
    pool = sorted(glob.glob(os.path.join(HERE, "cats", mood, "*.gif")))
    if not pool:
        return None
    memory = os.path.join(HERE, ".sticker-last.json")
    try:
        last = json.load(open(memory))
    except (OSError, ValueError):
        last = {}
    choice = random.choice([p for p in pool if p != last.get(mood)] or pool)
    last[mood] = choice
    json.dump(last, open(memory, "w"))
    return choice


def frames(mood):
    """[(image, seconds)] for the mood's GIF, or its PNG as a single frame."""
    gif = pick(mood) or pick(FALLBACK.get(mood, mood)) or os.path.join(HERE, "cats", mood + ".gif")
    if os.path.exists(gif):
        src = Image.open(gif)
        return [(f.convert("RGB"), max(0.04, f.info.get("duration", 80) / 1000))
                for f in ImageSequence.Iterator(src)]
    return [(Image.open(os.path.join(HERE, "cats", mood + ".png")).convert("RGB"), None)]


def wrap(text, face, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if face.getlength(trial) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def card(cat, mood, label, cell_w, cell_h, caption=None, frame=True):
    """Renders the sticker at exactly COLS x rows cells so nothing gets stretched.
    frame=False (Rex): no border, square corners, no outer margin; the Rex floating box
    around it is themed to CARD and supplies the rounded edge and the margin."""
    colour, default_caption = MOODS[mood]
    width = COLS * cell_w
    pad, radius, border = (10, 18, 3) if frame else (0, 14, 0)
    cat = cat.crop((3, 3, cat.width - 3, cat.height - 3))  # meme scans often carry a white edge
    inner = width - 2 * pad
    cat = cat.resize((inner, round(cat.height * inner / cat.width)), Image.LANCZOS)
    name_f, cap_f = font("Bold", 26), font("Regular", 21)
    captions = wrap(caption or default_caption, cap_f, inner - 8)[:3]
    height = pad + cat.height + 12 + 36 + 26 * len(captions) + (pad if frame else 4)
    rows = math.ceil(height / cell_h)
    height = rows * cell_h

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if frame:
        d.rounded_rectangle((0, 0, width - 1, height - 1), radius, fill=CARD, outline=colour, width=border)
    else:
        d.rectangle((0, 0, width - 1, height - 1), fill=CARD)
    mask = Image.new("L", cat.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cat.width - 1, cat.height - 1), max(4, radius - pad + 4), fill=255)
    img.paste(cat, (pad, pad), mask)
    y = pad + cat.height + 12
    tx = pad + 4 if frame else 2
    d.text((tx, y), label, font=name_f, fill=colour)
    for k, line in enumerate(captions):
        d.text((tx, y + 36 + 26 * k), line, font=cap_f, fill=CAPTION_GREY)
    return img, rows


# Rex mode: STICKER_TTY names the Claude pane's terminal (no tmux in between), so
# sequences go straight to it; geometry comes from the tty (or STICKER_GEOM in tests).
RAW_TTY = os.environ.get("STICKER_TTY")


def passthrough(tty, seq):
    with open(tty, "a" if RAW_TTY else "w") as f:
        if RAW_TTY:
            f.write(seq)
        else:
            f.write("\x1bPtmux;" + seq.replace("\x1b", "\x1b\x1b") + "\x1b\\")


def raw_geometry(tty):
    """cell width, cell height, columns of a terminal, without tmux."""
    if os.environ.get("STICKER_GEOM"):
        cols, cw, ch = (int(v) for v in os.environ["STICKER_GEOM"].split())
        return cw, ch, cols
    import fcntl, struct, termios
    fd = os.open(tty, os.O_RDONLY | os.O_NOCTTY)
    try:
        rows, cols, xp, yp = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
    finally:
        os.close(fd)
    return (xp // cols if xp else 17), (yp // rows if yp else 37), cols


def rex_play(tty, cards, clip, col, rows, hold):
    """Rex mode: Rex shows only images sent and placed in one command (a=T), so every
    frame is re-sent inline under one id, which replaces the shown frame in place."""
    def send(png):
        data = base64.b64encode(png).decode()
        parts = [data[i:i + 4096] for i in range(0, len(data), 4096)]
        head = "a=T,f=100,i=%d,p=1,c=%d,r=%d,C=1,q=2," % (IMAGE_ID, COLS, rows)
        return "".join("\x1b_G%sm=%d;%s\x1b\\" % (head if n == 0 else "", 1 if n < len(parts) - 1 else 0, part)
                       for n, part in enumerate(parts))

    def clear(*_):
        passthrough(tty, "\x1b_Ga=d,d=I,i=%d,q=2\x1b\\" % IMAGE_ID)
        sys.exit(0)

    signal.signal(signal.SIGTERM, clear)
    end, k = time.monotonic() + hold, 0
    while True:
        passthrough(tty, "\x1b7\x1b[2;%dH" % col + send(cards[k]) + "\x1b8")
        delay = clip[k][1]
        if delay is None or time.monotonic() + delay > end:
            time.sleep(max(0, end - time.monotonic()))
            break
        time.sleep(delay)
        k = (k + 1) % len(cards)
    clear()


def main():
    mood, label = sys.argv[1], sys.argv[2]
    hold = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 3.5
    caption = sys.argv[4] if len(sys.argv) > 4 else None
    try:  # newest sticker wins
        os.kill(int(open(PIDFILE).read()), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    open(PIDFILE, "w").write(str(os.getpid()))

    if RAW_TTY:
        tty = RAW_TTY
        cw, ch, cols = raw_geometry(tty)
    else:
        tty = tmux("display", "-p", "#{pane_tty}")
        cw, ch, cols = (int(v) for v in tmux("display", "-p", "#{client_cell_width} #{client_cell_height} #{client_width}").split())
    os.makedirs(CACHE, exist_ok=True)
    clip = frames(mood)
    ids = [IMAGE_ID + k for k in range(len(clip))]

    def clear(*_):
        passthrough(tty, "".join("\x1b_Ga=d,d=I,i=%d,q=2\x1b\\" % i for i in ids))
        sys.exit(0)

    signal.signal(signal.SIGTERM, clear)
    rows = 1
    rex_cards = []
    for k, (cat, _) in enumerate(clip):  # upload every frame, show none yet
        img, rows = card(cat, mood, label, cw or 17, ch or 37, caption)
        path = os.path.join(CACHE, "%s-%d.png" % (mood, k))
        img.save(path)
        if RAW_TTY:
            rex_cards.append(open(path, "rb").read())
        else:
            passthrough(tty, "\x1b_Gf=100,t=f,a=t,i=%d,q=2;%s\x1b\\" % (
                ids[k], base64.b64encode(path.encode()).decode()))

    if RAW_TTY:
        rex_play(tty, rex_cards, clip, max(1, cols - COLS - 1), rows, hold)
        return

    col = max(1, cols - COLS - 1)
    place = lambda i: "\x1b7\x1b[2;%dH\x1b_Ga=p,i=%d,p=1,c=%d,r=%d,C=1,q=2\x1b\\\x1b8" % (col, i, COLS, rows)
    end, k, shown = time.monotonic() + hold, 0, None
    while True:
        # new frame first, then drop the old placement: no blank flash between frames
        drop = "\x1b_Ga=d,d=i,i=%d,q=2\x1b\\" % shown if shown is not None and shown != ids[k] else ""
        passthrough(tty, place(ids[k]) + drop)
        shown = ids[k]
        delay = clip[k][1]
        if delay is None or time.monotonic() + delay > end:
            time.sleep(max(0, end - time.monotonic()))
            break
        time.sleep(delay)
        k = (k + 1) % len(clip)
    clear()


if __name__ == "__main__":
    main()
