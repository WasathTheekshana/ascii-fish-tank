#!/usr/bin/env python3
"""ASCII fish tank for the terminal. Standard library only."""

import argparse
import math
import os
import random
import select
import shutil
import signal
import sys
import time

VERSION = "0.1.0"

MIN_W, MIN_H = 30, 10
MAX_FISH = 60
MAX_BUBBLES = 200

# SGR colour codes. Bold plus a base colour shows as the bright colour on the
# Linux console, which only has 16 colours.
C_SURFACE = "1;36"
C_SAND = "33"
C_WEED = "32"
C_WEED_LIGHT = "1;32"
C_BUBBLE = "36"
C_CLOCK = "1;37"
C_DATE = "37"
C_STONE = "37"
C_CRAB = "1;31"
FISH_COLORS = ["1;31", "1;32", "1;33", "1;35", "1;36", "1;34", "31", "33", "35", "36"]

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

HINT = "q quit   c clock   s seconds   t 12/24h   p pause   +/- fish   ? help"


def _art(block):
    lines = block.strip("\n").split("\n")
    width = max(len(line) for line in lines)
    return [line.ljust(width) for line in lines]


_FLIP = str.maketrans("/\\()<>{}[]`'", "\\/)(><}{]['`")


def _mirror(lines):
    return [line[::-1].translate(_FLIP) for line in lines]


# All fish are drawn facing right. The left-facing version is mirrored.
_FISH_RIGHT = [
    _art(r"""
><>
"""),
    _art(r"""
><(('>
"""),
    _art(r"""
><{{{*>
"""),
    _art(r"""
   ,--.
>=<    o>
   `--'
"""),
    _art(r"""
    /\
   /  \_
><(    o>
   \  _/
    \/
"""),
    _art(r"""
        _,--.._
 \    ,'       `-.
  >==<          o >
 /    `._     _,-'
         `---'
"""),
]
FISH = [(art, _mirror(art)) for art in _FISH_RIGHT]

CASTLE = _art(r"""
  _   _   _
 | |_| |_| |
 |         |
 |   ,-.   |
 |   | |   |
 |___|_|___|
""")

CRAB = "V(o,o)V"

DIGITS = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": ["  #", "  #", "  #", "  #", "  #"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
    ":": [" ", "#", " ", "#", " "],
    " ": [" ", " ", " ", " ", " "],
}


class Fish:
    __slots__ = ("art", "w", "h", "x", "y", "vx", "color", "phase", "amp")


class State:
    def __init__(self, args):
        self.clock = not args.no_clock
        self.seconds = args.seconds
        self.h12 = args.h12
        self.paused = False
        self.hint_until = 0.0


class Tank:
    def __init__(self, n_fish, rng):
        self.rng = rng
        self.n_fish = n_fish  # None means pick a number from the tank size
        self.w = self.h = 0
        self.floor = 0
        self.t = 0.0
        self.fish = []
        self.bubbles = []
        self.sand = ""
        self.weeds = []
        self.pebbles = []
        self.stones = []
        self.castle_x = None
        self.crab_x = 0.0
        self.crab_v = 1.5

    def resize(self, w, h):
        rng = self.rng
        self.w, self.h = w, h
        self.floor = h - 2
        self.sand = "".join(rng.choice("..,,::;_") for _ in range(w))
        castle_w = len(CASTLE[0])
        big = w >= 70 and h >= 18
        self.castle_x = w - castle_w - 4 if big else None

        self.weeds = []
        x = rng.randint(1, 5)
        while x < w - 2:
            in_castle = (self.castle_x is not None
                         and self.castle_x - 2 <= x <= self.castle_x + castle_w)
            if not in_castle:
                height = rng.randint(2, max(2, min(8, h // 3)))
                colour = rng.choice((C_WEED, C_WEED_LIGHT))
                self.weeds.append((x, height, rng.uniform(0, 6.28), colour))
            x += rng.randint(3, 11)

        self.pebbles = [(rng.randrange(w), rng.choice("oO@*")) for _ in range(w // 12)]
        self.stones = [rng.randrange(2, max(3, w - 2)) for _ in range(1 + w // 70)]
        self.crab_x = float(rng.randrange(max(1, w - len(CRAB))))
        self.bubbles = []
        self.fish = []
        count = self.n_fish
        if count is None:
            count = max(3, min(25, w * h // 300))
        self.set_fish(count, scatter=True)

    def set_fish(self, count, scatter=False):
        count = max(0, min(MAX_FISH, count))
        del self.fish[count:]
        while len(self.fish) < count:
            fish = self._new_fish(scatter)
            if fish is None:
                break
            self.fish.append(fish)

    def _new_fish(self, scatter=False):
        rng = self.rng
        fits = [pair for pair in FISH
                if len(pair[0]) <= self.floor - 1 and len(pair[0][0]) <= self.w // 2]
        if not fits:
            return None
        right, left = rng.choice(fits)
        direction = rng.choice((-1, 1))
        f = Fish()
        f.art = right if direction > 0 else left
        f.w = len(right[0])
        f.h = len(right)
        f.vx = direction * rng.uniform(4, 14) / (1 + f.h * 0.35)
        f.y = rng.uniform(1, self.floor - f.h)
        if scatter:
            f.x = rng.uniform(0, self.w - f.w)
        else:
            f.x = float(-f.w if direction > 0 else self.w)
        f.color = rng.choice(FISH_COLORS)
        f.phase = rng.uniform(0, 6.28)
        f.amp = rng.choice((0.0, 0.0, 0.6, 1.0))
        return f

    def _bubble(self, x, y):
        if len(self.bubbles) < MAX_BUBBLES:
            rng = self.rng
            self.bubbles.append([x, y, rng.uniform(2.0, 4.5), rng.uniform(0, 6.28), y])

    def step(self, dt):
        rng = self.rng
        self.t += dt

        alive = []
        for f in self.fish:
            f.x += f.vx * dt
            if rng.random() < 0.25 * dt:
                mouth = f.x + f.w if f.vx > 0 else f.x - 1
                self._bubble(mouth, f.y + f.h // 2)
            if f.x > self.w or f.x + f.w < 0:
                f = self._new_fish()
            if f is not None:
                alive.append(f)
        self.fish = alive

        for sx in self.stones:
            if rng.random() < 2.5 * dt:
                self._bubble(float(sx), float(self.floor))
        for b in self.bubbles:
            b[1] -= b[2] * dt
        self.bubbles = [b for b in self.bubbles if b[1] >= 1]

        self.crab_x += self.crab_v * dt
        limit = self.w - len(CRAB) - 1
        if self.crab_x > limit:
            self.crab_x, self.crab_v = float(limit), -abs(self.crab_v)
        elif self.crab_x < 1:
            self.crab_x, self.crab_v = 1.0, abs(self.crab_v)

    def draw(self, state, now, hint):
        w, h, t, floor = self.w, self.h, self.t, self.floor
        chars = [[" "] * w for _ in range(h)]
        cols = [[None] * w for _ in range(h)]

        def put(x, y, ch, colour):
            if 0 <= x < w and 0 <= y < h:
                chars[y][x] = ch
                cols[y][x] = colour

        def text(x, y, s, colour):
            for i, ch in enumerate(s):
                if ch != " ":
                    put(x + i, y, ch, colour)

        for x in range(w):
            v = math.sin(x * 0.4 + t * 1.6) + 0.5 * math.sin(x * 0.13 - t * 0.9)
            put(x, 0, "^" if v > 0.9 else "~" if v > -0.4 else "-", C_SURFACE)

        if state.clock:
            self._draw_clock(text, state, now)

        for bx, by, _vy, phase, y0 in self.bubbles:
            risen = y0 - by
            ch = "." if risen < 2 else "o" if risen < 6 else "O"
            put(int(bx + math.sin(t * 3 + phase) * 0.8), int(by), ch, C_BUBBLE)

        chars[h - 1] = list(self.sand)
        cols[h - 1] = [C_SAND] * w
        for px, ch in self.pebbles:
            put(px, floor, ch, C_STONE)
        if self.castle_x is not None:
            top = floor - len(CASTLE) + 1
            for i, line in enumerate(CASTLE):
                text(self.castle_x, top + i, line, C_STONE)
        for wx, height, phase, colour in self.weeds:
            for i in range(height):
                lean = math.sin(t * 1.5 + phase + i * 0.6) > 0
                put(wx + (1 if lean else 0), floor - i, ")" if lean else "(", colour)
        text(int(self.crab_x), floor, CRAB, C_CRAB)

        for f in self.fish:
            fy = int(round(f.y + f.amp * math.sin(t * 1.3 + f.phase)))
            fy = max(1, min(floor - f.h + 1, fy))
            fx = math.floor(f.x)
            for i, line in enumerate(f.art):
                text(fx, fy + i, line, f.color)

        if state.paused:
            text(2, 1, "[paused]", C_CLOCK)
        if hint and w >= len(HINT) + 2:
            text((w - len(HINT)) // 2, h - 1, HINT, C_CLOCK)
        return chars, cols

    def _draw_clock(self, text, state, now):
        w, h = self.w, self.h
        hour = now.tm_hour
        suffix = ""
        if state.h12:
            suffix = " PM" if hour >= 12 else " AM"
            hour = hour % 12 or 12
        sep = ":" if state.seconds or now.tm_sec % 2 == 0 else " "
        label = "%02d%s%02d" % (hour, sep, now.tm_min)
        if state.seconds:
            label += ":%02d" % now.tm_sec
        date = "%s %d %s %d%s" % (DAYS[now.tm_wday], now.tm_mday,
                                  MONTHS[now.tm_mon - 1], now.tm_year, suffix)

        width = sum(len(DIGITS[ch][0]) * 2 + 2 for ch in label) - 2
        if w >= width + 4 and h >= 16:
            x = (w - width) // 2
            for ch in label:
                glyph = DIGITS[ch]
                for row, line in enumerate(glyph):
                    text(x, 2 + row, "".join(c * 2 for c in line), C_CLOCK)
                x += len(glyph[0]) * 2 + 2
            text((w - len(date)) // 2, 8, date, C_DATE)
        else:
            small = label + suffix
            if w >= len(small) + 4:
                text(w - len(small) - 2, 1, small, C_CLOCK)


def encode(chars, cols, colour):
    if not colour:
        return "".join(chars)
    out = []
    cur = None
    for ch, c in zip(chars, cols):
        if ch != " " and c != cur:
            out.append("\x1b[0;%sm" % c if c else "\x1b[0m")
            cur = c
        out.append(ch)
    if cur:
        out.append("\x1b[0m")
    return "".join(out)


def render(tank, state, colour, hint=False):
    w, h = tank.w, tank.h
    if w < MIN_W or h < MIN_H:
        msg = "terminal too small"[:w]
        lines = [" " * w for _ in range(h)]
        if h:
            lines[h // 2] = msg.center(w)
        return lines
    chars, cols = tank.draw(state, time.localtime(), hint)
    return [encode(chars[y], cols[y], colour) for y in range(h)]


def handle_keys(data, state, tank, now):
    """Apply key presses. Returns False when the user wants to quit."""
    if data[:1] == b"\x1b":
        # A lone Escape quits. Longer sequences are arrow or function keys.
        return len(data) > 1
    for byte in data:
        ch = chr(byte).lower() if byte < 128 else ""
        if ch in ("q", "\x03", "\x04"):
            return False
        if ch == "c":
            state.clock = not state.clock
        elif ch == "s":
            state.seconds = not state.seconds
        elif ch == "t":
            state.h12 = not state.h12
        elif ch in ("p", " "):
            state.paused = not state.paused
        elif ch in ("+", "="):
            tank.n_fish = min(MAX_FISH, len(tank.fish) + 1)
            tank.set_fish(tank.n_fish)
        elif ch in ("-", "_"):
            tank.n_fish = max(0, len(tank.fish) - 1)
            tank.set_fish(tank.n_fish)
        elif ch == "?":
            state.hint_until = 0.0 if state.hint_until > now else now + 8
    return True


def run(args, colour):
    try:
        import termios
        import tty
    except ImportError:
        sys.stderr.write("ascii-fish-tank needs Linux, macOS or WSL. Try --snapshot.\n")
        return 1

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write("ascii-fish-tank needs a terminal. Try --snapshot.\n")
        return 1

    def on_signal(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGHUP, on_signal)

    out = sys.stdout
    fd_in = sys.stdin.fileno()
    fd_out = out.fileno()
    saved = termios.tcgetattr(fd_in)
    tank = Tank(args.fish, random.Random())
    state = State(args)
    state.hint_until = time.monotonic() + 6
    frame = 1.0 / args.fps
    size = None
    prev = None
    last = time.monotonic()

    try:
        tty.setcbreak(fd_in)
        # Alternate screen, no cursor, no line wrap.
        out.write("\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J")
        while True:
            now = time.monotonic()
            dt = min(now - last, 0.25)
            last = now

            new_size = tuple(os.get_terminal_size(fd_out))
            if new_size != size:
                size = new_size
                tank.resize(*size)
                prev = None
                out.write("\x1b[0m\x1b[2J")
            if not state.paused:
                tank.step(dt)

            lines = render(tank, state, colour, hint=now < state.hint_until)
            buf = []
            for i, line in enumerate(lines):
                if prev is None or prev[i] != line:
                    buf.append("\x1b[%d;1H%s" % (i + 1, line))
            if buf:
                out.write("".join(buf))
                out.flush()
            prev = lines

            wait = max(0.0, frame - (time.monotonic() - now))
            ready, _, _ = select.select([fd_in], [], [], wait)
            if ready:
                data = os.read(fd_in, 64)
                if not data or not handle_keys(data, state, tank, time.monotonic()):
                    break
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        try:
            # The Linux console has no alternate screen, so clear it as well.
            out.write("\x1b[0m\x1b[2J\x1b[H\x1b[?7h\x1b[?25h\x1b[?1049l")
            out.flush()
        except OSError:
            pass
        termios.tcsetattr(fd_in, termios.TCSADRAIN, saved)
    return 0


def snapshot(args, colour):
    size = shutil.get_terminal_size((80, 24))
    tank = Tank(args.fish, random.Random())
    tank.resize(size.columns, size.lines - 1)
    for _ in range(50):
        tank.step(0.1)
    sys.stdout.write("\n".join(render(tank, State(args), colour)) + "\n")
    return 0


def _bounded(low, high):
    def convert(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("%r is not a whole number" % value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError("must be between %d and %d" % (low, high))
        return number
    return convert


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ascii-fish-tank",
        description="An ASCII fish tank that fills the terminal.",
        epilog="Keys: " + HINT,
    )
    parser.add_argument("--no-clock", action="store_true", help="start with the clock hidden")
    parser.add_argument("--seconds", action="store_true", help="show seconds on the clock")
    parser.add_argument("--12h", dest="h12", action="store_true", help="12 hour clock")
    parser.add_argument("--fish", type=_bounded(0, MAX_FISH), metavar="N",
                        help="number of fish (default depends on the terminal size)")
    parser.add_argument("--fps", type=_bounded(1, 30), default=10, metavar="N",
                        help="frames per second, 1 to 30 (default 10)")
    parser.add_argument("--no-color", action="store_true", help="draw without colour")
    parser.add_argument("--snapshot", action="store_true", help="print one frame and exit")
    parser.add_argument("--version", action="version", version="ascii-fish-tank " + VERSION)
    args = parser.parse_args(argv)

    colour = not args.no_color and "NO_COLOR" not in os.environ
    if args.snapshot:
        return snapshot(args, colour and sys.stdout.isatty())
    return run(args, colour)


if __name__ == "__main__":
    sys.exit(main())
