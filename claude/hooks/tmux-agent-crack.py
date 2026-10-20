#!/usr/bin/env python3
"""Shatters a failed tab's name like struck glass and circles it in red pen.

  tmux-agent-crack.py <window_id> [delay seconds | static]

Draws a kitty-graphics image exactly over the tab's cells in the status line
(plus the row above, where only the red pen stroke is drawn). The arrival is
animated: impact flash, cracks racing out, shards slipping, then the circle.
It then stays, following the tab if it moves, until the tab stops being
"failed". One process per window; the painter starts it.
"""
import base64
import fcntl
import glob
import math
import os
import random
import signal
import subprocess
import sys
import time

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:
    # The python3 first on PATH can lack Pillow (macOS's own /usr/bin/python3
    # once path_helper puts it first), so retry under Homebrew's.
    for py in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3"):
        if os.access(py, os.X_OK) and os.path.realpath(py) != os.path.realpath(sys.executable):
            os.execv(py, [py] + sys.argv)
    raise

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".crack-cache")
FPS = 30

BAR = (26, 26, 26, 255)
ROSE, AMBER = (217, 168, 160), (255, 193, 7)
CRACK, CRACK_SHADOW = (236, 242, 248, 215), (0, 0, 0, 150)
PEN = (255, 59, 48, 235)

# arrival choreography (seconds)
FLASH = 0.07
CRACK_AT, CRACK_LEN = 0.03, 0.22
SLIP_AT, SLIP_LEN = 0.18, 0.32
PEN_AT, PEN_LEN = 0.45, 0.5
TOTAL = PEN_AT + PEN_LEN


# ── easing ──
def clamp(t):
    return max(0.0, min(1.0, t))


def out_cubic(t):
    return 1 - (1 - clamp(t)) ** 3


def out_back(t, s=1.7):
    t = clamp(t) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def in_out_sine(t):
    return -(math.cos(math.pi * clamp(t)) - 1) / 2


# ── geometry ──
def strip_styles(fmt):
    out, i = [], 0
    while i < len(fmt):
        if fmt.startswith("#[", i):
            i = fmt.index("]", i) + 1
        elif fmt.startswith("##", i):
            out.append("#")
            i += 2
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


def tab_column(left_width, windows, target_index, sep=" "):
    """0-based column where the target tab's " N:name " starts, or None."""
    col = left_width
    for idx, name in windows:
        if idx == target_index:
            return col
        col += len(" %s:%s " % (idx, name)) + len(sep)
    return None


def font(bold, size):
    weight = "Bold" if bold else "Regular"
    for d in (os.path.expanduser("~/Library/Fonts"), "/Library/Fonts"):
        hits = glob.glob(os.path.join(d, "JetBrainsMono-%s.ttf" % weight))
        if hits:
            return ImageFont.truetype(hits[0], size)
    return ImageFont.load_default()


# ── the shattered label ──
class Shatter:
    def __init__(self, text, active, cw, ch, seed):
        self.text, self.cw, self.ch = text, cw, ch
        self.w, self.h = len(text) * cw, 2 * ch
        rng = random.Random(seed)
        # the name only (not the padding) takes the hit, a little left of centre
        self.impact = ((1.2 + rng.uniform(0.3, 0.5) * (len(text) - 2.4)) * cw, ch + ch * rng.uniform(0.35, 0.6))
        n = rng.randint(6, 8)
        base = rng.uniform(0, 2 * math.pi)
        self.angles = sorted((base + k * 2 * math.pi / n + rng.uniform(-0.25, 0.25)) % (2 * math.pi)
                             for k in range(n))
        self.cracks = [self._crack_path(a, rng) for a in self.angles]
        self.offsets = []
        for a0, a1 in zip(self.angles, self.angles[1:] + [self.angles[0] + 2 * math.pi]):
            mid = (a0 + a1) / 2
            push = rng.uniform(1.6, 3.4)
            self.offsets.append((math.cos(mid) * push, math.sin(mid) * push * 0.7, rng.uniform(0.62, 1.18)))
        self.rings = [(rng.choice(range(n)), rng.uniform(7, 11)) for _ in range(3)]
        self.pen = self._pen_path(rng)

        f = font(active, round(cw / 0.6))
        self.layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(self.layer)
        d.rectangle((0, ch, self.w, self.h), fill=BAR)
        top = ch + (ch - (f.getbbox("Hg")[3] - f.getbbox("Hg")[1])) / 2 - f.getbbox("Hg")[1]
        for i, c in enumerate(text):
            d.text((i * cw, top), c, font=f, fill=AMBER if active else ROSE)

    def _crack_path(self, angle, rng):
        x, y = self.impact
        pts, step = [(x, y)], 5.0
        while 0 <= x <= self.w and self.ch <= y <= self.h:
            a = angle + rng.uniform(-0.35, 0.35)
            x, y = x + math.cos(a) * step, y + math.sin(a) * step
            pts.append((x, y))
        return pts

    def _pen_path(self, rng):
        """A hand-drawn loop: wobbly, tilted, overshooting its own start."""
        rx, ry = self.w / 2 - 5, self.ch * 0.62
        cx, cy = self.w / 2, self.h - 4 - ry  # the loop's bottom sits just inside the tab row
        tilt, start = math.radians(rng.uniform(-4, 2)), rng.uniform(0.6, 1.2) * math.pi
        pts = []
        for k in range(97):
            t = start + k / 96 * 2.2 * math.pi  # 1.1 turns
            wob = 1 + 0.04 * math.sin(3 * t + 1.3) + 0.02 * math.sin(7 * t)
            ex, ey = math.cos(t) * rx * wob, math.sin(t) * ry * wob
            pts.append((min(self.w - 2, max(2, cx + ex * math.cos(tilt) - ey * math.sin(tilt))),
                        min(self.h - 2, cy + ex * math.sin(tilt) + ey * math.cos(tilt))))
        return pts

    def frame(self, t):
        """Image at t seconds into the arrival (t >= TOTAL is the resting frame)."""
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle((0, self.ch, self.w, self.h), fill=BAR)
        slip = out_back((t - SLIP_AT) / SLIP_LEN)
        px, py = self.impact
        far = 4 * self.w
        ends = self.angles[1:] + [self.angles[0] + 2 * math.pi]
        for a0, a1, (dx, dy, shade) in zip(self.angles, ends, self.offsets):
            mask = Image.new("L", (self.w, self.h), 0)
            wedge = [(px, py)] + [(px + math.cos(a) * far, py + math.sin(a) * far)
                                  for a in (a0, (a0 + a1) / 2, a1)]
            ImageDraw.Draw(mask).polygon(wedge, fill=255)
            shard = ImageChops.offset(self.layer, round(dx * slip), round(dy * slip))
            if slip > 0 and shade != 1:
                r, g, b, a = shard.split()
                k = 1 + (shade - 1) * clamp(slip)
                shard = Image.merge("RGBA", [ch.point(lambda v, k=k: min(255, v * k)) for ch in (r, g, b)] + [a])
            img.paste(shard, (0, 0), ImageChops.multiply(mask, shard.getchannel("A")))
        d.rectangle((0, 0, self.w, self.ch - 1), fill=(0, 0, 0, 0))  # row above stays clear

        grow = out_cubic((t - CRACK_AT) / CRACK_LEN)
        for pts in self.cracks:
            n = max(2, round(len(pts) * grow))
            if grow > 0:
                seg = pts[:n]
                d.line([(x, y + 1) for x, y in seg], fill=CRACK_SHADOW, width=1)
                d.line(seg[:4], fill=CRACK, width=2)  # thicker where the blow landed
                d.line(seg, fill=CRACK, width=1)
        if t >= SLIP_AT:
            for k, r in self.rings:
                a0, a1 = self.angles[k], (self.angles + [self.angles[0] + 2 * math.pi])[k + 1]
                d.arc((px - r, py - r, px + r, py + r), math.degrees(a0), math.degrees(a1),
                      fill=CRACK, width=1)
        if t < FLASH + 0.12:  # composited, so it fades out instead of punching a hole
            k = 1 - clamp((t - FLASH) / 0.12) if t > FLASH else clamp(t / FLASH)
            r = 2 + 6 * out_cubic(t / (FLASH + 0.12))
            glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse((px - r, py - r, px + r, py + r), fill=(255, 255, 255, round(235 * k)))
            img.alpha_composite(glow)
            d = ImageDraw.Draw(img)
        pen = in_out_sine((t - PEN_AT) / PEN_LEN)
        if pen > 0:
            n = max(2, round(len(self.pen) * pen))
            d.line(self.pen[:n], fill=PEN, width=3, joint="curve")
        return img


# ── tmux / terminal plumbing ──
def clean(raw):
    """Drop only the trailing newline: leading/trailing spaces are layout here."""
    return raw.rstrip("\n")


def tmux(*args):
    return clean(subprocess.run(["tmux", *args], capture_output=True, text=True).stdout)


def passthrough(tty, seq):
    try:
        with open(tty, "w") as f:
            f.write("\x1bPtmux;" + seq.replace("\x1b", "\x1b\x1b") + "\x1b\\")
    except OSError:
        pass


def where(wid):
    """(state, text, active, row, col 1-based, cell w/h, tty) or None when not on screen."""
    info = tmux("display", "-p", "-t", wid, "#{@agent}\t#{window_index}\t#{window_name}\t#{window_active}\t#{session_name}")
    if not info:
        return None
    state, idx, name, active, session = (info.split("\t") + [""] * 5)[:5]
    geo = tmux("display", "-p", "#{session_name}\t#{client_height}\t#{client_cell_width}\t#{client_cell_height}\t"
                               "#{pane_tty}\t#{status-position}\t#{status-left-length}\t#{window-status-separator}")
    shown, height, cw, ch, tty, pos, left_max, sep = (geo.split("\t") + [""] * 8)[:8]
    if state != "failed":
        return ("gone",)
    if session != shown or pos != "bottom":
        return ("hidden",)
    left = strip_styles(tmux("display", "-p", "-t", wid, "#{E:status-left}"))[: int(left_max or 10)]
    windows = [tuple(l.split("\t", 1)) for l in tmux("list-windows", "-t", session, "-F",
                                                        "#{window_index}\t#{window_name}").splitlines()]
    col = tab_column(len(left), windows, idx, sep)
    if col is None:
        return ("hidden",)
    return ("shown", " %s:%s " % (idx, name), active == "1", int(height), col + 1, int(cw or 17), int(ch or 37), tty)


def main():
    wid = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "0"
    lock = open(os.path.join(HERE, ".crack-%s.lock" % wid.lstrip("@")), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return  # already cracked
    os.makedirs(CACHE, exist_ok=True)
    base = 5000 + int(wid.lstrip("@")) * 64
    tty, placed, shatter, seed = None, None, None, random.random()

    def put(image_id, path, spot):
        _, text, _, row, col, _, _, _ = spot
        passthrough(tty, "\x1b_Gf=100,t=f,a=t,i=%d,q=2;%s\x1b\\" % (image_id, base64.b64encode(path.encode()).decode()))
        passthrough(tty, "\x1b7\x1b[%d;%dH\x1b_Ga=p,i=%d,p=1,c=%d,r=2,C=1,z=1,q=2\x1b\\\x1b8" % (
            row - 1, col, image_id, len(text)))

    def clear():
        if tty:
            passthrough(tty, "".join("\x1b_Ga=d,d=I,i=%d,q=2\x1b\\" % (base + k) for k in range(40)))

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # so finally still removes the image
    if mode != "static":
        time.sleep(float(mode))
    animate = mode != "static"
    try:
        while True:
            spot = where(wid)
            if spot is None or spot[0] == "gone":
                break
            if spot[0] == "hidden":
                if placed:
                    clear()
                    placed = None
                time.sleep(0.5)
                continue
            _, text, active, row, col, cw, ch, tty = spot
            key = (text, active, row, col, cw, ch)
            if key != (placed and placed[0]):
                if not shatter or (text, active, cw, ch) != shatter[0]:
                    shatter = ((text, active, cw, ch), Shatter(text, active, cw, ch, seed))
                s = shatter[1]
                if animate:  # arrival: each frame goes in fresh, the previous one is dropped
                    t0, k = time.monotonic(), 0
                    while True:
                        t = time.monotonic() - t0
                        path = os.path.join(CACHE, "%s-%d.png" % (wid.lstrip("@"), k % 2))
                        s.frame(t).save(path)
                        put(base + k % 2 + 1, path, spot)
                        passthrough(tty, "\x1b_Ga=d,d=I,i=%d,q=2\x1b\\" % (base + (k + 1) % 2 + 1))
                        k += 1
                        if t >= TOTAL:
                            break
                        time.sleep(max(0, 1 / FPS - (time.monotonic() - t0 - t)))
                    animate = False
                path = os.path.join(CACHE, "%s-rest.png" % wid.lstrip("@"))
                s.frame(TOTAL + 1).save(path)
                clear()
                put(base, path, spot)
                placed = (key, time.monotonic())
            elif time.monotonic() - placed[1] > 1.0:
                # re-place now and then: a full-screen clear in the terminal wipes images
                put(base, os.path.join(CACHE, "%s-rest.png" % wid.lstrip("@")), spot)
                placed = (key, time.monotonic())
            time.sleep(0.25)
    finally:
        clear()


if __name__ == "__main__":
    main()
