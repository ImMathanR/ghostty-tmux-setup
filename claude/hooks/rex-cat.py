#!/usr/bin/env python3
"""Play a cat GIF in the current terminal with the kitty graphics protocol.

Used for Rex's floating "sticker" layer (the Rex counterpart of tmux-agent-sticker.py).
  rex-cat.py --probe            print "images: yes" / "images: no" (asks the terminal)
  rex-cat.py GIF [--seconds S]  play GIF fitted to the terminal, then exit
Each frame is re-sent under the same image id, which replaces the shown image in place.
"""
import base64, glob, io, os, random, select, sys, termios, time, tty

ESC = "\x1b"


def apc(ctrl, payload=b""):
    """One kitty graphics command; payload base64 in 4096-byte chunks."""
    data = base64.b64encode(payload).decode()
    if not data:
        return f"{ESC}_G{ctrl}{ESC}\\"
    chunks = [data[i:i + 4096] for i in range(0, len(data), 4096)]
    out = []
    for n, ch in enumerate(chunks):
        more = 1 if n < len(chunks) - 1 else 0
        head = f"{ctrl},m={more}" if n == 0 else f"m={more}"
        out.append(f"{ESC}_G{head};{ch}{ESC}\\")
    return "".join(out)


def probe(timeout=1.0):
    """Ask for kitty graphics support; DA1 right after tells us when to stop waiting."""
    fd = os.open("/dev/tty", os.O_RDWR)
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        os.write(fd, f"{ESC}_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA{ESC}\\{ESC}[c".encode())
        buf, end = b"", time.time() + timeout
        while time.time() < end and b"[?" not in buf:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                buf += os.read(fd, 1024)
        return b"_Gi=31;OK" in buf
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


def rounded(fr, frac=0.07):
    from PIL import Image, ImageDraw
    m = Image.new("L", fr.size, 0)
    r = max(4, int(min(fr.size) * frac))
    ImageDraw.Draw(m).rounded_rectangle((0, 0, fr.size[0] - 1, fr.size[1] - 1), r, fill=255)
    fr.putalpha(Image.composite(fr.getchannel("A"), m, m))
    return fr


def frames(path, max_px):
    from PIL import Image
    im = Image.open(path)
    out = []
    try:
        while True:
            fr = im.convert("RGBA")
            fr.thumbnail((max_px, max_px))
            fr = rounded(fr)
            b = io.BytesIO()
            fr.save(b, "PNG")
            out.append((b.getvalue(), max(0.04, im.info.get("duration", 100) / 1000)))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return out


def cached_frames(path, max_px, cache_root=None):
    """frames(), cached as PNG files + delays per GIF (keyed by name, size, mtime), so a
    replay reads bytes and never imports PIL."""
    root = cache_root or os.path.expanduser("~/.cache/rex-cats")
    st = os.stat(path)
    d = os.path.join(root, "v2-%s-%d-%d-%d" % (os.path.basename(path), st.st_size, int(st.st_mtime), max_px))
    idx = os.path.join(d, "delays.txt")
    if os.path.exists(idx):
        with open(idx) as f:
            delays = [float(x) for x in f.read().split()]
        out = []
        for i, dl in enumerate(delays):
            with open(os.path.join(d, "%03d.png" % i), "rb") as f:
                out.append((f.read(), dl))
        return out
    fs = frames(path, max_px)
    tmp = d + ".tmp%d" % os.getpid()
    os.makedirs(tmp, exist_ok=True)
    for i, (png, _) in enumerate(fs):
        with open(os.path.join(tmp, "%03d.png" % i), "wb") as f:
            f.write(png)
    with open(os.path.join(tmp, "delays.txt"), "w") as f:
        f.write(" ".join(str(dl) for _, dl in fs))
    try:
        os.rename(tmp, d)
    except OSError:
        pass  # another player cached it first
    return fs


def placement(png, max_scale=1.6):
    """Fit the image in the terminal keeping its aspect, upscaling at most max_scale
    (the GIFs are ~320 px; more just blurs), centered. Returns cols, rows, c, r, x, y."""
    import fcntl, struct
    w, h = struct.unpack(">II", png[16:24])  # PNG IHDR
    try:
        rows, cols, xp, yp = struct.unpack("HHHH", fcntl.ioctl(1, termios.TIOCGWINSZ, b"\0" * 8))
    except OSError:
        cols, rows = os.get_terminal_size(); xp = yp = 0
    if not xp or not yp:
        xp, yp = cols * 9, rows * 18
    cw, ch = xp / cols, yp / rows
    scale = min(xp / w, yp / h, max_scale)
    c = max(1, min(cols, round(w * scale / cw)))
    r = max(1, min(rows, round(h * scale / ch)))
    return cols, rows, c, r, (cols - c) // 2 + 1, (rows - r) // 2 + 1


def play(path, seconds):
    sys.stdout.write(f"{ESC}[?25l")  # hide the cursor before the first frame
    sys.stdout.flush()
    fs = cached_frames(path, 360)
    cols, rows, c, r, x, y = placement(fs[0][0])
    pos = f"{ESC}[{y};{x}H"
    sys.stdout.write(f"{ESC}[?25l{ESC}[2J")
    end = time.time() + seconds
    try:
        while time.time() < end:
            for png, delay in fs:
                sys.stdout.write(pos + apc(f"a=T,f=100,i=7,p=1,q=2,c={c},r={r},C=1", png))
                sys.stdout.flush()
                time.sleep(delay)
                if time.time() >= end:
                    break
    finally:
        sys.stdout.write(apc("a=d,d=I,i=7,q=2") + f"{ESC}[?25h")
        sys.stdout.flush()


def png_size(png):
    import struct
    return struct.unpack(">II", png[16:24])


def card_frames(mood, label, cw, ch, gif=None, frame=True):
    """The Ghostty tmux sticker card (tmux-agent-sticker.card) for every GIF frame, as
    PNG bytes at exactly 18 x rows cells of cw x ch pixels. The card is drawn once and
    only the cat is pasted per frame, so a 40-frame GIF renders in about a second."""
    import importlib.util
    from PIL import Image, ImageDraw
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("sticker", os.path.join(here, "tmux-agent-sticker.py"))
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    if gif:
        from PIL import ImageSequence
        with Image.open(gif) as src:
            clip = [(f.convert("RGB"), max(0.04, f.info.get("duration", 80) / 1000)) for f in ImageSequence.Iterator(src)]
    else:
        clip = st.frames(mood)
    template, rows = st.card(clip[0][0], mood, label, cw, ch, frame=frame)
    pad, radius = (10, 18) if frame else (0, 14)  # as in tmux-agent-sticker.card
    inner = template.width - 2 * pad
    out = []
    for k, (cat, delay) in enumerate(clip):
        cat = cat.crop((3, 3, cat.width - 3, cat.height - 3))
        cat = cat.resize((inner, round(cat.height * inner / cat.width)), Image.LANCZOS)
        mask = Image.new("L", cat.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cat.width - 1, cat.height - 1), max(4, radius - pad + 4), fill=255)
        fr = template.copy()
        fr.paste(cat, (pad, pad), mask)
        b = io.BytesIO()
        fr.save(b, "PNG", compress_level=1)
        out.append((b.getvalue(), delay or 4.0))
    return out, rows


def cell_px():
    import fcntl, struct
    rows, cols, xp, yp = struct.unpack("HHHH", fcntl.ioctl(1, termios.TIOCGWINSZ, b"\0" * 8))
    return (xp // cols if xp else 17), (yp // rows if yp else 37), cols, rows


def fill_cell(cols, cw):
    """Cell width to hand card(): it draws 18 cells wide, so this stretches it to `cols`."""
    return (cols * cw) // 18


def pick_gif(mood):
    pool = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cats", mood, "*.gif"))
    return random.choice(pool) if pool else None


def fit_card(mood, label, cw, ch, cols, rows_avail, gif=None, max_upscale=2.0):
    """Largest card that fits cols x rows_avail cells: fill the width (upscaling the
    cat at most max_upscale x its source width), then shrink until its height fits too.
    Returns (frames, rows, width_in_cells)."""
    gif = gif or pick_gif(mood)
    src_w = None
    if gif and max_upscale:
        from PIL import Image
        with Image.open(gif) as im:
            src_w = im.width
    c = cols
    if src_w is not None and max_upscale:
        while c > 6 and 18 * fill_cell(c, cw) - 20 > max_upscale * src_w:
            c -= 1
    while True:
        fs, rows = card_frames(mood, label, fill_cell(c, cw), ch, gif)
        if rows <= rows_avail or c <= 6:
            return fs, rows, c
        c -= 1


def settled_size(get, step=0.03, stable=0.25, limit=1.5):
    """Poll get() until its value has not changed for `stable` seconds (or `limit` passes).
    Rex opens a layer's terminal at 80x24 and resizes it to the layer a moment later."""
    end = time.time() + limit
    last, since = get(), time.time()
    while time.time() < end:
        time.sleep(step)
        cur = get()
        if cur != last:
            last, since = cur, time.time()
        elif time.time() - since >= stable:
            break
    return last


def play_card(mood, label, seconds, gif=None, get_size=cell_px, out=sys.stdout,
              sleep=time.sleep, settle_step=0.03, settle_stable=0.25,
              settle_limit=1.5, now=None):
    """Play the tmux card filling this terminal's width, centred vertically.
    Re-reads the terminal size between frames and refits if the host resizes the layer."""
    clock = now or time.time
    out.write(f"{ESC}[?25l{ESC}[2J")
    out.flush()
    gif = gif or pick_gif(mood)
    size = settled_size(get_size, step=settle_step, stable=settle_stable, limit=settle_limit)

    def usable(sz):
        return sz[2] >= 6 and sz[3] >= 4

    def fit_for(sz):
        cw, ch, cols, rows_avail = sz
        fs, rows, c = fit_card(mood, label, cw, ch, cols, rows_avail, gif)
        x, y = max(1, (cols - c) // 2 + 1), max(1, (rows_avail - rows) // 2 + 1)
        return fs, rows, c, x, y

    end = clock() + seconds
    # Rex can report 0 or 1 cells for a moment while it lays the layer out; a card can't
    # be drawn that small (PIL refuses a zero-width resize), so wait for a usable size.
    while not usable(size) and clock() < end:
        sleep(settle_step)
        size = get_size()
    if not usable(size):
        return
    fs, rows, c, x, y = fit_for(size)
    i = 0
    try:
        while clock() < end:
            cur = get_size()
            if cur != size and usable(cur):
                size = cur
                fs, rows, c, x, y = fit_for(size)
                out.write(f"{ESC}[2J" + apc("a=d,d=I,i=7,q=2"))
                out.flush()
                i = i % len(fs)
            png, delay = fs[i]
            out.write(f"{ESC}[{y};{x}H" + apc(f"a=T,f=100,i=7,p=1,q=2,c={c},r={rows},C=1", png))
            out.flush()
            sleep(delay)
            i = (i + 1) % len(fs)
    finally:
        out.write(apc("a=d,d=I,i=7,q=2") + f"{ESC}[?25h")
        out.flush()


def prepare_card(mood, label, cw, ch, cols, gif=None, cache_root=None, max_upscale=2.0, frame=True):
    """Render the card for every frame at exactly cols x rows cells of cw x ch px into a
    cache dir (PNG files + delays.txt) and return (dir, cols, rows). cols shrinks so the
    cat is never stretched past max_upscale x its source width. A later call with the same
    inputs only reads the dir, so the floating box can be sized before it opens."""
    import hashlib, random
    gif = gif or pick_gif(mood)
    root = cache_root or os.path.expanduser("~/.cache/rex-cats")
    st = os.stat(gif)
    key = hashlib.sha1(repr((os.path.abspath(gif), st.st_mtime, st.st_size, mood, label,
                             cw, ch, cols, max_upscale, frame)).encode()).hexdigest()[:16]
    d = os.path.join(root, "card-" + key)
    meta = os.path.join(d, "card.txt")
    if os.path.exists(meta):
        c, r = open(meta).read().split()
        return d, int(c), int(r)
    from PIL import Image
    with Image.open(gif) as im:
        src_w = im.width
    c = cols
    while c > 6 and c * cw - 20 > max_upscale * src_w:
        c -= 1
    fs, rows = card_frames(mood, label, max(1, (c * cw) // 18), ch, gif, frame=frame)
    tmp = d + ".tmp%d" % os.getpid()
    os.makedirs(tmp, exist_ok=True)
    delays = []
    for k, (png, delay) in enumerate(fs):
        w, h = png_size(png)
        if (w, h) != (c * cw, rows * ch):
            fr = Image.open(io.BytesIO(png)).resize((c * cw, rows * ch), Image.LANCZOS)
            b = io.BytesIO(); fr.save(b, "PNG", compress_level=1); png = b.getvalue()
        open(os.path.join(tmp, "%03d.png" % k), "wb").write(png)
        delays.append("%.3f" % delay)
    open(os.path.join(tmp, "delays.txt"), "w").write("\n".join(delays))
    open(os.path.join(tmp, "card.txt"), "w").write("%d %d" % (c, rows))
    try:
        os.rename(tmp, d)
    except OSError:  # another process won the race; use its copy
        import shutil; shutil.rmtree(tmp, ignore_errors=True)
    return d, c, rows


def show_card(path, cols, rows, seconds, out=sys.stdout, sleep=time.sleep, now=None):
    """Replay a prepared card at the top-left cell, scaled to exactly cols x rows cells."""
    clock = now or time.time
    names = sorted(f for f in os.listdir(path) if f.endswith(".png"))
    delays = [float(x) for x in open(os.path.join(path, "delays.txt")).read().split()]
    fs = [(open(os.path.join(path, n), "rb").read(), delays[k] if k < len(delays) else 0.08)
          for k, n in enumerate(names)]
    out.write(f"{ESC}[?25l{ESC}[2J")
    end = clock() + seconds
    i = 0
    try:
        while clock() < end and fs:
            png, delay = fs[i]
            out.write(f"{ESC}[1;1H" + apc(f"a=T,f=100,i=7,p=1,q=2,c={cols},r={rows},C=1", png))
            out.flush()
            sleep(delay)
            i = (i + 1) % len(fs)
    finally:
        out.write(apc("a=d,d=I,i=7,q=2") + f"{ESC}[?25h")
        out.flush()


if __name__ == "__main__":
    if sys.argv[1:2] == ["--probe"]:
        print("images:", "yes" if probe() else "no")
    elif sys.argv[1:2] == ["--prepare"]:  # --prepare MOOD LABEL CW CH COLS -> "DIR COLS ROWS"
        m, l, cw, ch, cols = sys.argv[2], sys.argv[3], *map(int, sys.argv[4:7])
        print(*prepare_card(m, l, cw, ch, cols, frame="--bare" not in sys.argv))
    elif sys.argv[1:2] == ["--show"]:  # --show DIR COLS ROWS [--seconds S]
        secs = float(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 4
        show_card(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), secs)
    elif sys.argv[1:2] == ["--card"]:  # --card MOOD LABEL [--seconds S] [--gif FILE]
        secs = float(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 4
        gif = sys.argv[sys.argv.index("--gif") + 1] if "--gif" in sys.argv else None
        play_card(sys.argv[2], sys.argv[3], secs, gif)
    else:
        secs = float(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 6
        play(sys.argv[1], secs)
