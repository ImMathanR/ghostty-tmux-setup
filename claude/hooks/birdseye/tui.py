#!/usr/bin/env python3
"""Birdseye: every tmux tab as a live card, in plain terminal text.

Each card shows what the tab's agent is saying right now (its latest lines, in
their real colours, without Claude's input box), framed by its state:
  heavy pink   needs you          heavy red   failed
  mint         done               sage        done, unseen for 10+ minutes
  amber        the tab you came from          spinner     working
  cyan badge   subagents running

  mouse   click a card to go there
  keys    1-99 go to that tab   arrows + enter pick one   z full view of one
          + - fewer/more cards per row   0 back to normal   a all sessions   q back

Text, not images: tmux keeps this tab's screen, so switching here is instant,
and only rows that changed are rewritten. Started by tmux-birdseye-open.sh.
"""
import math
import os
import re
import select
import signal
import sys
import termios
import time
import tty

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ansi  # noqa: E402
import model  # noqa: E402

PIDFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".birdseye.pid")
MOUSE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

RGB = {"amber": (255, 193, 7), "pink": (255, 126, 182), "mint": (95, 215, 167), "sage": (125, 154, 143),
       "red": (255, 90, 54), "cyan": (90, 209, 255), "frame": (70, 70, 74), "text": (190, 190, 190),
       "muted": (124, 124, 128), "white": (234, 234, 234), "bg": (18, 18, 18)}
STATE = {"ask": "pink", "failed": "red", "done": "mint", "cold": "sage", "working": "amber"}
LIGHT = dict(zip("tl tr bl br h v".split(), "╭ ╮ ╰ ╯ ─ │".split()))
HEAVY = dict(zip("tl tr bl br h v".split(), "┏ ┓ ┗ ┛ ━ ┃".split()))


def fg(name, bold=False):
    return "\x1b[%s38;2;%d;%d;%dm" % ("1;" if bold else "", *RGB[name])


RESET = "\x1b[0m"



def subagents_of(tab):
    """A teammate pane shows the same agents as its lead, so count the most any pane shows."""
    return max((p["subagents"] for p in tab["panes"]), default=0)


def out(s):
    os.write(sys.stdout.fileno(), s.encode())


class Birdseye:
    def __init__(self):
        self.snap, self.tabs = None, []
        self.per_row, self.show_all = None, False   # None = pick automatically
        self.selected, self.full = 0, None           # full = pane id shown full-screen
        self.shown = []                              # rows currently on screen
        self.window, self.visible, self.checked, self.fetched = "", True, 0.0, 0.0
        self.typed = None                            # first digit of a two-digit tab number
        self.reflowed = {}                           # (pane, text, width) -> wrapped lines

    # ── data ──
    def refresh(self):
        self.snap = model.snapshot()
        wins = {}
        for p in self.snap["panes"]:
            if p["birdseye"] or p["sidebar"] or (not self.show_all and p["session"] != self.snap["client_session"]):
                continue
            wins.setdefault(p["window_id"], {"id": p["window_id"], "session": p["session"], "index": p["window_index"],
                                             "name": p["window_name"], "agent": p["agent"],
                                             "agent_age": p["agent_age"], "panes": []})["panes"].append(p)
        current = self.snap["client_session"]
        self.tabs = sorted(wins.values(), key=lambda w: (w["session"] != current, w["session"], w["index"]))
        self.selected = min(self.selected, max(0, len(self.tabs) - 1))

    def look(self):
        raw = model.tmux("display", "-p", "-t", os.environ.get("TMUX_PANE", ""), "#{window_id}", ";",
                         "list-clients", "-F", "#{window_id}").split()
        if raw:
            self.window, visible = raw[0], raw[0] in raw[1:]
            if visible and not self.visible:
                self.shown = []  # repaint everything once we're back on screen
            self.visible = visible

    # ── layout ──
    def grid(self, cols, rows):
        n = max(1, len(self.tabs))
        if self.per_row:
            per = max(1, min(self.per_row, n))
        else:  # the most cards per row that still leaves each one readable
            per = max((p for p in range(1, 7) if cols // p >= 42 or p == 1), key=lambda p: (
                min(cols // p, 110) * min((rows // math.ceil(n / p)) - 2, 30)))
        lines = math.ceil(n / per)
        return per, cols // per, max(4, rows // lines)

    # ── one card ──
    def card(self, tab, w, h, selected, now):
        state = model.state_of(tab)
        current = tab["id"] == self.snap["client_window"]
        colour = "white" if selected else STATE.get(state) if state in ("ask", "failed", "done", "cold") \
            else "amber" if current else "frame"
        box = HEAVY if state in ("ask", "failed") else LIGHT
        bold = state in ("ask", "failed") or current or selected
        # title in the top border, state on the right
        name = "%d:%s" % (tab["index"], tab["name"])
        subs = subagents_of(tab)
        right = []
        if subs:
            right.append((" %d subagent%s " % (subs, "" if subs == 1 else "s"), "\x1b[1;38;2;18;18;18;48;2;90;209;255m"))
        meta = model.describe(tab)
        if state == "working":
            meta = SPINNER[int(now * 8) % len(SPINNER)] + " " + meta
        elif state == "failed":
            meta = "✗ " + meta
        if meta:
            right.append((" " + meta + " ", fg(STATE.get(state, "muted"), state in ("ask", "failed"))))
        if len(tab["panes"]) > 1:
            right.append((" %d panes " % len(tab["panes"]), fg("muted")))
        right_w = sum(ansi.visible_width(t) for t, _ in right)
        # top border = "╭─ " + name + " " + fill + right + "─╮", exactly w cells
        name_w = max(4, min(ansi.visible_width(name), w - 7 - right_w))
        title = ansi.clip(name, name_w, pad=True)
        fill = w - 6 - name_w - right_w
        top = (fg(colour, bold) + box["tl"] + box["h"] + " " + RESET
               + (fg("amber", True) if current else fg("white", True)) + title
               + fg(colour, bold) + " " + box["h"] * max(0, fill) + RESET
               + "".join(style + t + RESET for t, style in right)
               + fg(colour, bold) + box["h"] + box["tr"] + RESET)
        rows = [top]
        # body: the pane with Claude in it (else the active one), its latest lines
        pane = next((p for p in tab["panes"] if p["claude"]), None) or \
            next((p for p in tab["panes"] if p["pane_active"]), tab["panes"][0])
        wrapped = self.reflow(pane, w - 4)
        body = wrapped[-(h - 2):]
        body = [""] * (h - 2 - len(body)) + body
        faded = len(wrapped) > h - 2
        side = fg(colour, bold) + box["v"] + RESET
        for k, line in enumerate(body):
            dim = "\x1b[2m" if faded and k < 2 else ""  # older lines recede at the top
            rows.append(side + " " + dim + ansi.clip(line.replace("\x1b[0m", "\x1b[0m" + dim), w - 4) + " " + side)
        rows.append(fg(colour, bold) + box["bl"] + box["h"] * (w - 2) + box["br"] + RESET)
        return rows

    # ── the cats ──
    def since(self, tab, state, now):
        """When this tab entered its state (first sight counts as long ago: no celebration on open)."""
        seen = self.changed.get(tab["id"])
        if seen is None or seen[0] != state:
            self.changed[tab["id"]] = (state, now if seen is not None else now - 999)
        return self.changed[tab["id"]][1]

    def reflow(self, pane, width):
        """The pane's content re-wrapped to the card: whole lines, not cut off at the edge."""
        key = (pane["pane_id"], hash(pane["text"]), width)
        if key not in self.reflowed:
            if len(self.reflowed) > 200:
                self.reflowed.clear()
            lines = ansi.unwrap(model.content_lines(pane["text"]), pane["width"])
            self.reflowed[key] = [part for line in lines for part in (ansi.wrap(line, width) or [""])]
        return self.reflowed[key]

    def frame(self, cols, rows, now):
        if self.full:
            return self.full_view(cols, rows)
        if not self.tabs:
            return ["", "  " + fg("muted") + "No other tabs yet." + RESET] + [""] * (rows - 2)
        per, w, h = self.grid(cols, rows)
        screen = [""] * rows
        for k, tab in enumerate(self.tabs):
            r, c = divmod(k, per)
            if (r + 1) * h > rows:
                break
            for i, line in enumerate(self.card(tab, w, h, k == self.selected, now)):
                screen[r * h + i] += line
        return [s + "\x1b[0K" for s in screen]

    def full_view(self, cols, rows):
        """One pane, all of it, live: the close-up."""
        pane = next((p for t in self.tabs for p in t["panes"] if p["pane_id"] == self.full), None)
        if not pane:
            self.full = None
            return self.frame(cols, rows, time.time())
        lines = pane["text"].split("\n")[-rows:]
        return [ansi.clip(l, cols) + "\x1b[0K" for l in lines] + ["\x1b[0K"] * (rows - len(lines))

    def hint(self, cols):
        tab = self.tabs[self.selected] if self.tabs and self.selected < len(self.tabs) else None
        if self.full:
            text = fg("amber", True) + " full view " + fg("muted") + "  enter go there   esc back to all tabs"
        else:
            count = lambda s: sum(model.state_of(t) == s for t in self.tabs)
            parts = [fg("text", True) + " " + (self.snap["client_session"] if self.snap else "")]
            for n, word, c in ((count("ask"), "need you", "pink"), (count("failed"), "failed", "red"),
                               (count("working"), "busy", "amber"), (count("done"), "done", "mint")):
                if n:
                    parts.append(fg(c) + "%d %s" % (n, word))
            if tab:
                parts.append(fg("white") + "%d:%s" % (tab["index"], tab["name"]))
            parts.append(fg("muted") + "click or enter to go   z full view   + - cards per row   0 reset   q back")
            text = "   ".join(parts)
        return ansi.clip(text, cols)

    def paint(self):
        cols, rows = os.get_terminal_size()
        now = time.time()
        screen = self.frame(cols, rows - 1, now) + [self.hint(cols)]
        if len(self.shown) != len(screen):
            self.shown = [None] * len(screen)
        buf = []
        for i, line in enumerate(screen):  # only rows that changed
            if line != self.shown[i]:
                buf.append("\x1b[%d;1H%s" % (i + 1, line))
                self.shown[i] = line
        if buf:
            out("".join(buf))

    # ── actions ──
    def go(self, tab, pane=None):
        pane = pane or next((p for p in tab["panes"] if p["pane_active"]), tab["panes"][0])
        self.full = None
        model.focus(pane["pane_id"])

    def open_tab(self, index):
        for k, t in enumerate(self.tabs):
            if t["index"] == index and t["session"] == self.snap["client_session"]:
                self.selected = k
                return self.go(t)

    def card_at(self, x, y):
        cols, rows = os.get_terminal_size()
        per, w, h = self.grid(cols, rows - 1)
        k = (y - 1) // h * per + (x - 1) // w
        return k if (x - 1) // w < per and 0 <= k < len(self.tabs) else None

    def handle(self, data):
        cols, rows = os.get_terminal_size()
        for m in MOUSE.finditer(data):
            b, x, y, kind = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            if self.full or y >= rows:
                continue
            k = self.card_at(x, y)
            if k is None:
                continue
            if b == 35 or (b == 0 and kind == "M"):
                self.selected = k
            elif b == 0 and kind == "m":
                self.selected = k
                return self.go(self.tabs[k])
        keys = MOUSE.sub("", data)
        if keys == "\x1b":
            if self.full:
                self.full = None
            else:
                model.tmux("last-window")
            return
        per = self.grid(cols, rows - 1)[0]
        moves = {"\x1b[A": -per, "\x1b[B": per, "\x1b[C": 1, "\x1b[D": -1, "k": -per, "j": per, "l": 1, "h": -1}
        for seq, d in moves.items():
            if seq in keys and not self.full:
                self.selected = max(0, min(len(self.tabs) - 1, self.selected + d * keys.count(seq)))
                keys = keys.replace(seq, "")
        keys = re.sub(r"\x1b\[?[0-9;]*[A-Za-z~]?", "", keys)
        for key in keys:
            tab = self.tabs[self.selected] if self.tabs else None
            if key == "q":
                self.full = None
                model.tmux("last-window")
            elif key in "\r\n" and tab:
                pane = next((p for p in tab["panes"] if p["pane_id"] == self.full), None)
                return self.go(tab, pane)
            elif key == "z" and tab:
                self.full = None if self.full else (next((p for p in tab["panes"] if p["claude"]), None)
                                                    or tab["panes"][0])["pane_id"]
                self.shown = []
            elif key in "+=":
                self.per_row = max(1, (self.per_row or self.grid(cols, rows - 1)[0]) - 1)
                self.shown = []
            elif key == "-":
                self.per_row = min(6, (self.per_row or self.grid(cols, rows - 1)[0]) + 1)
                self.shown = []
            elif key == "a":
                self.show_all = not self.show_all
                self.refresh()
                self.shown = []
            elif key.isdigit():
                if self.typed and time.time() - self.typed[1] < 0.6:
                    first, self.typed = self.typed[0], None
                    return self.open_tab(first * 10 + int(key))
                if any(str(t["index"]).startswith(key) and t["index"] >= 10 for t in self.tabs):
                    self.typed = (int(key), time.time())  # maybe a two-digit tab: wait a beat
                elif key == "0":  # back to normal: automatic card size, this session only, no full view
                    self.per_row, self.show_all, self.full = None, False, None
                    self.refresh()
                    self.shown = []
                else:
                    return self.open_tab(int(key))

    def run(self):
        signal.signal(signal.SIGUSR1, lambda *_: setattr(self, "checked", 0.0))
        signal.signal(signal.SIGWINCH, lambda *_: setattr(self, "shown", []))
        with open(PIDFILE, "w") as f:  # tmux's tab-switch hook signals exactly this process
            f.write(str(os.getpid()))
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        tty.setraw(fd)
        out("\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h\x1b[2J")
        try:
            self.refresh()
            while True:
                now = time.time()
                if now - self.checked > (0.5 if self.visible else 2.0):
                    self.look()
                    self.checked = now
                if self.visible:
                    if now - self.fetched > 0.5:
                        self.refresh()
                        self.fetched = now
                    self.paint()
                if self.typed and now - self.typed[1] >= 0.6:  # no second digit came
                    first, self.typed = self.typed[0], None
                    self.open_tab(first)
                ready, _, _ = select.select([fd], [], [], 0.12)
                if ready:
                    data = os.read(fd, 4096).decode(errors="ignore")
                    if "\x03" in data:
                        break
                    self.handle(data)
                    if self.visible:
                        self.paint()  # answer input straight away
        finally:
            out("\x1b[?1006l\x1b[?1003l\x1b[?1002l\x1b[?1000l\x1b[?25h\x1b[0m\x1b[?1049l")
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    Birdseye().run()
