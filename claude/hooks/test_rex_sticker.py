"""tmux-agent-sticker.py in Rex mode (STICKER_TTY set): same 18-cell card, written straight
to the pane's terminal (no tmux, no passthrough wrapper). Run: python3 test_rex_sticker.py"""
import os, subprocess, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class RexSticker(unittest.TestCase):
    def test_card_goes_straight_to_the_tty_at_18_cells(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "tty")
            open(out, "w").close()
            env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
            env.update(STICKER_TTY=out, STICKER_GEOM="120 17 37")  # cols, cell w, cell h
            subprocess.run(["python3", os.path.join(HERE, "tmux-agent-sticker.py"), "done", "workspace", "0.2"],
                           env=env, check=True, timeout=60)
            data = open(out).read()
            self.assertNotIn("\x1bPtmux;", data, "no tmux passthrough in Rex mode")
            self.assertIn("\x1b_Ga=T,f=100,", data, "each frame sent and shown in one command (a=T)")
            self.assertNotIn("a=p,", data, "Rex ignores separate placements")
            self.assertNotIn("t=f", data, "Rex ignores file-path images: send the data inline")
            self.assertIn("c=18,", data, "card is 18 cells wide, like tmux")
            self.assertIn("\x1b[2;%dH" % (120 - 18 - 1), data, "top-right corner")
            self.assertIn("a=d,d=I", data, "cleared at the end")


if __name__ == "__main__":
    unittest.main()
