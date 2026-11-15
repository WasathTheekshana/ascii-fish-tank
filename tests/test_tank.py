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


def make_tank(w, h, seed=1):
    tank = aft.Tank(None, random.Random(seed))
    tank.resize(w, h)
    return tank


class RenderTest(unittest.TestCase):
    def test_frames_fit_every_size(self):
        sizes = [(1, 1), (5, 3), (30, 10), (31, 11), (80, 24), (200, 60), (300, 12), (40, 50)]
        for w, h in sizes:
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
    def setUp(self):
        self.tank = make_tank(80, 24, seed=2)
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
