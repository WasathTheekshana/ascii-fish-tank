import os
import random
import re
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ascii_fish_tank as aft  # noqa: E402


class Args:
    no_clock = False
    seconds = True
    h12 = True
    fish = None
    style = "pixel"
    night = "off"


def make_tank(w, h, seed=1, kind=None):
    tank = (kind or aft.AsciiTank)(None, random.Random(seed))
    tank.resize(w, h)
    return tank


SGR = re.compile("\x1b" + r"\[[0-9;]*m")
SIZES = [(1, 1), (5, 3), (30, 10), (31, 11), (80, 24), (200, 60), (300, 12), (40, 50)]


class PixelTest(unittest.TestCase):
    def test_frames_fit_every_size_and_colour_mode(self):
        blocks = set(" " + aft.UPPER + aft.LOWER + aft.FULL)
        for mode in ("true", "256", "16"):
            encoder = aft.PixelEncoder(mode)
            for w, h in SIZES:
                tank = make_tank(w, h, kind=aft.PixelTank)
                state = aft.State(Args)
                state.clock = False
                for step in range(200):
                    tank.step(0.1)
                    if step % 50:
                        continue
                    lines = aft.render_pixel(tank, state, encoder)
                    self.assertEqual(len(lines), h)
                    for line in lines:
                        plain = SGR.sub("", line)
                        self.assertEqual(len(plain), w, (mode, w, h))
                        if w >= aft.MIN_W and h >= aft.MIN_H:
                            self.assertLessEqual(set(plain), blocks)

    def test_text_is_drawn_over_the_pixels(self):
        tank = make_tank(120, 40, kind=aft.PixelTank)
        state = aft.State(Args)
        state.paused = True
        lines = aft.render_pixel(tank, state, aft.PixelEncoder("true"), hint=True)
        plain = [SGR.sub("", line) for line in lines]
        self.assertIn("[paused]", plain[1])
        # Spaces in the text leave the pixels showing.
        tail = " ".join(plain[-3:]).replace(aft.UPPER, " ")
        self.assertIn("q quit", tail)
        self.assertIn("? help", tail)
        self.assertTrue(all(len(line) == 120 for line in plain))

    def test_night_and_monitor_in_every_colour_mode(self):
        metrics = [("CPU", "23%", 0.23), ("TEMP", "91C", 0.94), ("LOAD", "0.42", None)]
        for mode in ("true", "256", "16"):
            for w, h in ((30, 10), (80, 24), (160, 50)):
                tank = make_tank(w, h, kind=aft.PixelTank)
                state = aft.State(Args)
                state.night, state.monitor, state.metrics = "on", True, metrics
                for _ in range(30):
                    tank.step(0.1)
                lines = aft.render_pixel(tank, state, aft.PixelEncoder(mode))
                plain = [SGR.sub("", line) for line in lines]
                self.assertTrue(all(len(line) == w for line in plain), (mode, w, h))
                self.assertIn("CPU", "".join(plain))
                self.assertNotIn("\x1b", "".join(plain))

    def test_night_is_darker_but_the_clock_still_glows(self):
        day, night = aft.PixelEncoder("true"), aft.PixelEncoder("true")
        night.set_night(True)
        water = aft.water_colour(0.2)
        self.assertLess(night._shade(water), day._shade(water))
        self.assertEqual(night._shade(aft.TEXT), aft.TEXT & aft.RGB)

    def test_night_follows_the_clock_in_auto(self):
        state = aft.State(Args)
        state.night = "auto"
        noon = time.struct_time((2026, 1, 1, 12, 0, 0, 3, 1, 0))
        late = time.struct_time((2026, 1, 1, 23, 0, 0, 3, 1, 0))
        self.assertFalse(aft.is_night(state, noon))
        self.assertTrue(aft.is_night(state, late))

    def test_clock_size_changes_what_is_drawn(self):
        tank = make_tank(160, 50, kind=aft.PixelTank)
        state = aft.State(Args)
        now = time.localtime()
        lit = []
        for size in (1, 4):
            state.clock_size = size
            rows, _text = tank.draw(state, now, False)
            lit.append(sum(1 for row in rows for c in row if c & aft.EMISSIVE))
            self.assertEqual(tank.clock_u, size)
        self.assertGreater(lit[1], lit[0] * 4)
        state.clock = state.date = False
        rows, _text = tank.draw(state, now, False)
        self.assertEqual(sum(1 for row in rows for c in row if c & aft.EMISSIVE), 0)

    def test_hint_wraps_to_the_width(self):
        for width in (30, 60, 80, 200):
            lines = aft.hint_lines(width)
            self.assertTrue(all(len(line) <= width - 2 for line in lines), width)
            self.assertEqual("  ".join(lines), aft.HINT)

    def test_system_monitor_never_raises(self):
        monitor = aft.SysMon()
        for _ in range(2):
            for label, value, fraction in monitor.sample():
                self.assertTrue(label.isalpha() and value)
                self.assertTrue(fraction is None or isinstance(fraction, float))

    def test_every_fish_has_a_body_and_a_mirror_image(self):
        for name, spec in aft.SPECIES.items():
            for layer in (0, 1, 2):
                length = max(6, int(spec["len"][0] * aft.LAYER_SCALE[layer]))
                right, left, w, h = aft.fish_sprites(name, length, layer)
                self.assertEqual(len(right), len(aft.TAIL_FRAMES))
                for a, b in zip(right, left):
                    self.assertEqual(len(a), h)
                    count = sum(len(cols) for row in a for _x, cols in row)
                    self.assertGreater(count, length)
                    self.assertEqual(count, sum(len(cols) for row in b for _x, cols in row))

    def test_food_is_eaten_or_cleared(self):
        tank = make_tank(100, 30, kind=aft.PixelTank)
        tank.feed()
        self.assertTrue(tank.flakes)
        for _ in range(400):
            tank.step(0.1)
        self.assertEqual(tank.flakes, [])

    def test_fish_stay_in_the_water(self):
        tank = make_tank(120, 40, kind=aft.PixelTank)
        tank.feed()
        for _ in range(600):
            tank.step(0.1)
            for fish in tank.fish:
                self.assertGreaterEqual(fish.y, 3)
                self.assertLessEqual(fish.y + fish.h, tank.floor)


class RenderTest(unittest.TestCase):
    def test_frames_fit_every_size(self):
        for w, h in SIZES:
            tank = make_tank(w, h)
            state = aft.State(Args)
            for step in range(300):
                tank.step(0.1)
                if step % 50:
                    continue
                self.assertEqual(len(aft.render(tank, state, True, hint=True)), h)
                plain = aft.render(tank, state, False)
                self.assertEqual(len(plain), h)
                for line in plain:
                    self.assertEqual(len(line), w, (w, h))
                    self.assertTrue(line.isascii())

    def test_small_terminal_shows_message(self):
        tank = make_tank(40, 5)
        frame = aft.render(tank, aft.State(Args), False)
        self.assertIn("terminal too small", "".join(frame))

    def test_clock_can_be_hidden(self):
        tank = make_tank(80, 24)
        state = aft.State(Args)
        self.assertIn("##", "".join(aft.render(tank, state, False)))
        state.clock = False
        self.assertNotIn("##", "".join(aft.render(tank, state, False)))

    def test_mirror_flips_twice_to_the_same_art(self):
        for right, left in aft.FISH:
            self.assertEqual(aft._mirror(left), right)


class KeyTest(unittest.TestCase):
    kind = aft.AsciiTank

    def setUp(self):
        self.tank = make_tank(80, 24, seed=2, kind=self.kind)
        self.state = aft.State(Args)

    def press(self, data):
        return aft.handle_keys(data, self.state, self.tank, 0.0)

    def test_toggles(self):
        self.press(b"c")
        self.assertFalse(self.state.clock)
        self.press(b"C")
        self.assertTrue(self.state.clock)
        self.press(b"p")
        self.assertTrue(self.state.paused)
        self.press(b"v")
        self.assertEqual(self.state.style, "ascii")
        self.press(b"f")
        self.press(b"d")
        self.assertFalse(self.state.date)
        self.press(b"m")
        self.assertTrue(self.state.monitor)
        self.press(b"n")
        self.assertEqual(self.state.night, "on")
        self.press(b"n")
        self.assertEqual(self.state.night, "off")

    def test_clock_size_keys_stay_in_range(self):
        if self.tank.style == "pixel":
            # One frame, so the tank knows how large the clock can be.
            aft.render_pixel(self.tank, self.state, aft.PixelEncoder("true"))
        self.press(b"]" * 30)
        top = getattr(self.tank, "clock_max", 0)
        self.assertEqual(self.state.clock_size, top)
        self.press(b"[" * 30)
        self.assertEqual(self.state.clock_size, 1 if top else 0)

    def test_fish_count_stays_in_range(self):
        self.press(b"+" * 200)
        self.assertEqual(len(self.tank.fish), aft.MAX_FISH)
        self.press(b"-" * 200)
        self.assertEqual(len(self.tank.fish), 0)

    def test_quit_keys(self):
        for data in (b"q", b"Q", b"\x1b", b"\x03"):
            self.assertFalse(self.press(data))

    def test_unknown_input_is_ignored(self):
        clock = self.state.clock
        for data in (b"\x1b[A", b"\x1b[C", b"\xff\xfe\x00zzz", b"\x1bOP"):
            self.assertTrue(self.press(data))
        self.assertEqual(self.state.clock, clock)


class PixelKeyTest(KeyTest):
    kind = aft.PixelTank


class OptionTest(unittest.TestCase):
    def test_out_of_range_numbers_are_rejected(self):
        for argv in (["--fps", "0"], ["--fps", "99"], ["--fish", "-1"], ["--fish", "x"]):
            with self.assertRaises(SystemExit):
                with open(os.devnull, "w") as devnull:
                    stderr, sys.stderr = sys.stderr, devnull
                    try:
                        aft.main(argv)
                    finally:
                        sys.stderr = stderr

    def test_nix_package_version_matches(self):
        with open(os.path.join(ROOT, "package.nix")) as handle:
            found = re.search(r'version = "([^"]+)"', handle.read())
        self.assertEqual(found.group(1), aft.VERSION)


if __name__ == "__main__":
    unittest.main()
