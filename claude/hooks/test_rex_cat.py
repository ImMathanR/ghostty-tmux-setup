"""rex-cat.py frame cache: the first play decodes the GIF, later plays read cached PNGs
without importing PIL (so the floating layer shows the cat almost at once).
Run: python3 test_rex_cat.py"""
import importlib.util, io, os, re, sys, tempfile, time, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rexcat", os.path.join(HERE, "rex-cat.py"))
rexcat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rexcat)
GIF = sorted(os.listdir(os.path.join(HERE, "cats", "done")))[0]
GIF = os.path.join(HERE, "cats", "done", GIF)


class FrameCache(unittest.TestCase):
    def test_second_load_uses_cache_and_matches(self):
        with tempfile.TemporaryDirectory() as d:
            first = rexcat.cached_frames(GIF, 360, cache_root=d)
            self.assertGreater(len(first), 1)
            self.assertTrue(os.listdir(d), "cache dir should be filled")
            saved = {k: sys.modules.pop(k) for k in ("PIL", "PIL.Image") if k in sys.modules}
            try:
                second = rexcat.cached_frames(GIF, 360, cache_root=d)
                self.assertEqual(first, second)
                self.assertNotIn("PIL.Image", sys.modules, "cached load must not import PIL")
            finally:
                sys.modules.update(saved)

    def test_cache_is_rebuilt_when_gif_changes(self):
        with tempfile.TemporaryDirectory() as d:
            rexcat.cached_frames(GIF, 360, cache_root=d)
            k1 = set(os.listdir(d))
            st = os.stat(GIF)
            os.utime(GIF, (st.st_atime, st.st_mtime + 1))
            try:
                rexcat.cached_frames(GIF, 360, cache_root=d)
                self.assertNotEqual(set(os.listdir(d)) - k1, set())
            finally:
                os.utime(GIF, (st.st_atime, st.st_mtime))


class CardFrames(unittest.TestCase):
    """The floating layer shows the same 18-cell card as Ghostty tmux, at 1:1 pixels."""

    def test_card_frames_are_18_cells_wide_and_quick(self):
        t = time.time()
        fs, rows = rexcat.card_frames("done", "workspace", 17, 37)
        took = time.time() - t
        self.assertGreater(len(fs), 1)
        w, h = rexcat.png_size(fs[0][0])
        self.assertEqual(w, 18 * 17)
        self.assertEqual(h, rows * 37)
        self.assertLess(took, 6, "rendering every frame must not stall the sticker")


class FillsTheBox(unittest.TestCase):
    def test_card_spans_the_whole_box_width(self):
        cw, ch, cols = 17, 37, 23
        fs, rows = rexcat.card_frames("done", "hooks", rexcat.fill_cell(cols, cw), ch)
        w, _ = rexcat.png_size(fs[0][0])
        self.assertGreaterEqual(w, cols * cw - 18)  # within one cell-share of rounding
        self.assertLessEqual(w, cols * cw)


class FitsBothWays(unittest.TestCase):
    def test_card_fits_a_short_box(self):
        fs, rows, c = rexcat.fit_card("done", "hooks", 17, 37, cols=23, rows_avail=9)
        self.assertLessEqual(rows, 9)
        self.assertLessEqual(c, 23)


class SettledSize(unittest.TestCase):
    """A new Rex layer starts at 80x24 and is resized a moment later; centre on the final size."""

    def test_waits_for_the_resize(self):
        sizes = iter([(17, 37, 80, 24)] * 3 + [(19, 40, 30, 20)] * 100)
        got = rexcat.settled_size(lambda: next(sizes), step=0.001, stable=0.005, limit=1)
        self.assertEqual(got, (19, 40, 30, 20))

    def test_gives_up_after_the_limit(self):
        n = iter(range(10**6))
        got = rexcat.settled_size(lambda: (17, 37, next(n), 24), step=0.001, stable=0.05, limit=0.02)
        self.assertEqual(len(got), 4)


class PlayCardResize(unittest.TestCase):
    """If the host resizes the layer after settled_size, play_card refits and redraws."""

    def test_survives_a_transient_tiny_size(self):
        """Rex can report 0 or 1 columns for a moment while it lays the layer out; the
        player must keep the last good card instead of crashing (that left the box empty)."""
        seq = [(17, 37, 23, 15)] * 6 + [(17, 37, 0, 0), (17, 37, 1, 1)] * 3 + [(17, 37, 23, 15)] * 1000
        it = iter(seq)
        t = [0.0]

        def fake_sleep(dt):
            t[0] += dt

        buf = io.StringIO()
        rexcat.play_card(
            "done", "hooks", seconds=1.5, gif=GIF,
            get_size=lambda: next(it), out=buf, sleep=fake_sleep, now=lambda: t[0],
            settle_step=0.001, settle_stable=0.002, settle_limit=0.005,
        )
        cols = [int(c) for c in re.findall(r"\x1b_Ga=T,[^;]*?c=(\d+)", buf.getvalue())]
        self.assertGreater(len(cols), 3)
        self.assertTrue(all(c >= 6 for c in cols), cols)

    def test_starts_even_if_first_size_is_tiny(self):
        it = iter([(17, 37, 0, 0)] * 5 + [(17, 37, 23, 15)] * 1000)
        t = [0.0]
        buf = io.StringIO()
        rexcat.play_card(
            "done", "hooks", seconds=1.5, gif=GIF,
            get_size=lambda: next(it), out=buf, sleep=lambda dt: t.__setitem__(0, t[0] + dt), now=lambda: t[0],
            settle_step=0.001, settle_stable=0.0001, settle_limit=0.0001,
        )
        self.assertIn("a=T", buf.getvalue())

    def test_refits_when_layer_resizes_mid_playback(self):
        reads = 0

        def fake_size():
            nonlocal reads
            reads += 1
            return (17, 37, 6, 12) if reads <= 8 else (17, 37, 23, 15)

        t = [0.0]

        def fake_sleep(dt):
            t[0] += dt

        buf = io.StringIO()
        rexcat.play_card(
            "done", "hooks", seconds=1.5, gif=GIF,
            get_size=fake_size, out=buf, sleep=fake_sleep, now=lambda: t[0],
            settle_step=0.001, settle_stable=0.002, settle_limit=0.005,
        )
        data = buf.getvalue()
        placements = list(re.finditer(r"\x1b_Ga=T,[^;]*?c=(\d+),r=(\d+),C=1", data))
        self.assertGreaterEqual(len(placements), 2)
        cols_seen = [int(m.group(1)) for m in placements]
        self.assertEqual(cols_seen[0], 6, "should start at the initial 6-col size")
        self.assertGreater(cols_seen[-1], 6, "last placement should use the resized width")

        first_big_idx = next(i for i, c in enumerate(cols_seen) if c > 6)
        last_small = placements[first_big_idx - 1]
        first_big = placements[first_big_idx]
        between = data[last_small.end():first_big.start()]
        self.assertIn("\x1b[2J", between, "should clear screen after size change")
        self.assertIn("a=d,d=I,i=7", between, "should delete old image after size change")

        big_c, big_r = int(first_big.group(1)), int(first_big.group(2))
        want_x = max(1, (23 - big_c) // 2 + 1)
        want_y = max(1, (15 - big_r) // 2 + 1)
        self.assertIn(f"\x1b[{want_y};{want_x}H", between, "should recompute x/y centring")

    def test_resize_keeps_same_gif_when_picked_randomly(self):
        reads = 0

        def fake_size():
            nonlocal reads
            reads += 1
            return (17, 37, 6, 12) if reads <= 8 else (17, 37, 23, 15)

        t = [0.0]

        def fake_sleep(dt):
            t[0] += dt

        gifs_used = []
        real_fit = rexcat.fit_card

        def spy_fit(mood, label, cw, ch, cols, rows_avail, gif=None, *args, **kwargs):
            gifs_used.append(gif)
            return real_fit(mood, label, cw, ch, cols, rows_avail, gif, *args, **kwargs)

        buf = io.StringIO()
        with mock.patch.object(rexcat, "fit_card", side_effect=spy_fit):
            rexcat.play_card(
                "done", "hooks", seconds=1.5, gif=None,
                get_size=fake_size, out=buf, sleep=fake_sleep, now=lambda: t[0],
                settle_step=0.001, settle_stable=0.002, settle_limit=0.005,
            )
        self.assertEqual(len(gifs_used), 2, "should fit once initially and once on resize")
        self.assertIsNotNone(gifs_used[0])
        self.assertEqual(gifs_used[0], gifs_used[1], "refit must reuse the same GIF")


class UpscaleCap(unittest.TestCase):
    """Big displays must not over-upscale low-res GIFs or use bilinear blur."""

    def test_caps_cat_upscale_on_big_box(self):
        from PIL import Image
        gif = os.path.join(HERE, "cats", "done", "02-dancing-cat.gif")
        with Image.open(gif) as im:
            src_w = im.width
        self.assertLessEqual(abs(src_w - 260), 10)
        fs, rows, c = rexcat.fit_card("done", "hooks", 17, 37, cols=60, rows_avail=60, gif=gif)
        card_w, _ = rexcat.png_size(fs[0][0])
        self.assertEqual(card_w, 18 * rexcat.fill_cell(c, 17))
        cat_w = card_w - 20
        self.assertLessEqual(cat_w, 2.0 * src_w)
        self.assertGreaterEqual(c, 6)
        self.assertLess(c, 60)

    def test_max_upscale_never_shrinks_below_6(self):
        gif = os.path.join(HERE, "cats", "done", "02-dancing-cat.gif")
        fs, rows, c = rexcat.fit_card("done", "hooks", 17, 37, cols=20, rows_avail=60, gif=gif, max_upscale=0.1)
        self.assertEqual(c, 6)

    def test_card_frames_uses_lanczos(self):
        from PIL import Image
        resamples = []
        orig_resize = Image.Image.resize

        def spy_resize(self_im, size, resample=None, *args, **kwargs):
            resamples.append(resample)
            return orig_resize(self_im, size, resample, *args, **kwargs)

        with mock.patch.object(Image.Image, "resize", spy_resize):
            rexcat.card_frames("done", "hooks", 17, 37, gif=GIF)
        self.assertTrue(resamples)
        self.assertTrue(all(r == Image.LANCZOS for r in resamples), f"expected LANCZOS, got {set(resamples)}")


class PrepareAndShow(unittest.TestCase):
    """The layer launcher renders the card first (--prepare), sizes the Rex box to it, then
    the box only replays the ready PNGs (--show), so the cat appears at once and fits."""

    def test_prepare_renders_exact_cells_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as d:
            t = time.time()
            path, cols, rows = rexcat.prepare_card("done", "hooks", 17, 38, 18, gif=GIF, cache_root=d)
            first = time.time() - t
            self.assertEqual(cols, 18)
            pngs = sorted(f for f in os.listdir(path) if f.endswith(".png"))
            self.assertGreater(len(pngs), 1)
            w, h = rexcat.png_size(open(os.path.join(path, pngs[0]), "rb").read())
            self.assertEqual((w, h), (cols * 17, rows * 38))
            t = time.time()
            again = rexcat.prepare_card("done", "hooks", 17, 38, 18, gif=GIF, cache_root=d)
            self.assertEqual(again, (path, cols, rows))
            self.assertLess(time.time() - t, max(0.05, first / 5), "second prepare must reuse the cache")

    def test_prepare_caps_the_upscale(self):
        with tempfile.TemporaryDirectory() as d:
            from PIL import Image
            src_w = Image.open(GIF).width
            _, cols, _ = rexcat.prepare_card("done", "hooks", 17, 38, 80, gif=GIF, cache_root=d)
            self.assertLessEqual(cols * 17 - 20, 2.0 * src_w)
            self.assertGreaterEqual(cols, 6)

    def test_show_plays_cached_frames_at_the_origin_without_pil(self):
        with tempfile.TemporaryDirectory() as d:
            path, cols, rows = rexcat.prepare_card("done", "hooks", 17, 38, 18, gif=GIF, cache_root=d)
            saved = {k: sys.modules.pop(k) for k in ("PIL", "PIL.Image") if k in sys.modules}
            t = [0.0]
            buf = io.StringIO()
            rexcat.show_card(path, cols, rows, 1.0, out=buf,
                             sleep=lambda dt: t.__setitem__(0, t[0] + dt), now=lambda: t[0])
            data = buf.getvalue()
            self.assertNotIn("PIL.Image", sys.modules)
            self.assertIn(f"\x1b[1;1H\x1b_Ga=T,f=100,i=7,p=1,q=2,c={cols},r={rows},C=1", data)
            self.assertTrue(data.rstrip().endswith("\x1b[?25h"))
            sys.modules.update(saved)  # restore for later tests


class Frameless(unittest.TestCase):
    """In Rex the floating box is the card: no border of its own, the box takes the card's
    background (terminal set_theme), so there is no frame inside a frame."""

    def test_bare_card_has_no_outline(self):
        import importlib.util as iu
        spec = iu.spec_from_file_location("st", os.path.join(HERE, "tmux-agent-sticker.py"))
        st = iu.module_from_spec(spec); spec.loader.exec_module(st)
        from PIL import Image
        cat = Image.new("RGB", (200, 150), (255, 0, 0))
        img, rows = st.card(cat, "done", "hooks", 17, 38, frame=False)
        bg = tuple(int(st.CARD[i:i + 2], 16) for i in (1, 3, 5))
        edge = img.getpixel((1, img.height - 2))[:3]  # below the cat, where a border would be
        corner = img.getpixel((0, 0))[:3]
        self.assertEqual(edge, bg)
        self.assertEqual(corner, bg, "square corners: the Rex box rounds them")

    def test_prepare_bare_is_cached_separately(self):
        with tempfile.TemporaryDirectory() as d:
            a = rexcat.prepare_card("done", "hooks", 17, 38, 18, gif=GIF, cache_root=d)
            b = rexcat.prepare_card("done", "hooks", 17, 38, 18, gif=GIF, cache_root=d, frame=False)
            self.assertNotEqual(a[0], b[0])
            self.assertEqual(a[1:], b[1:])


if __name__ == "__main__":
    unittest.main()
