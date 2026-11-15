import os
import random
import re
import sys
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
        self.assertIn("q quit", plain[-1].replace(aft.UPPER, " "))
        self.assertTrue(any("20" in line for line in plain))  # the year in the date
        self.assertTrue(all(len(line) == 120 for line in plain))

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
