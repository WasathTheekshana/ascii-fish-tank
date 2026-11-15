#!/usr/bin/env python3
"""Fish tank for the terminal. Standard library only.

Two styles share one simulation loop. The pixel style draws two coloured
pixels per character cell with half blocks. The ascii style uses plain
characters and works on any terminal.
"""

import argparse
import math
import os
import random
import select
import shutil
import signal
import sys
import time
from itertools import groupby

VERSION = "0.3.0"

MIN_W, MIN_H = 30, 10
MAX_FISH = 60
MAX_BUBBLES = 200

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

HINT_KEYS = ["q quit", "c clock", "d date", "[ ] clock size", "s seconds", "t 12/24h",
             "n night", "m monitor", "f feed", "v style", "1-4 scene", "p pause", "+/- fish", "? help"]
HINT = "  ".join(HINT_KEYS)


class State:
    def __init__(self, args):
        self.clock = not args.no_clock
        self.seconds = args.seconds
        self.h12 = args.h12
        self.style = getattr(args, "style", "ascii")
        self.scene = getattr(args, "scene", "reef")
        self.date = not getattr(args, "no_date", False)
        self.clock_size = getattr(args, "clock_size", None) or 0  # 0 picks a size
        self.night = getattr(args, "night", "auto")  # "auto", "on" or "off"
        self.monitor = getattr(args, "monitor", False)
        self.metrics = []  # (label, value, fraction or None), filled by SysMon
        self.paused = False
        self.hint_until = 0.0


def clock_text(state, now):
    """Returns (time label, date line) for the clock."""
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
    return label, date, suffix


def is_night(state, now):
    if state.night == "auto":
        return now.tm_hour >= 19 or now.tm_hour < 6
    return state.night == "on"


def hint_lines(width):
    """The key list, wrapped to fit the width."""
    lines, cur = [], ""
    for item in HINT_KEYS:
        longer = cur + "  " + item if cur else item
        if cur and len(longer) > width - 2:
            lines.append(cur)
            cur = item
        else:
            cur = longer
    lines.append(cur)
    return lines


class SysMon:
    """Reads CPU, memory, disk, temperature and load. Linux gives all five.

    Each reading is skipped when the system does not offer it.
    """

    def __init__(self):
        self.cpu_prev = None
        self.rows = []
        self.at = None

    def update(self, now):
        if self.at is None or now - self.at >= 2:
            self.at = now
            self.rows = self.sample()

    @staticmethod
    def _read(path):
        with open(path, "rb") as handle:
            return handle.read(4096).decode("ascii", "replace")

    def _cpu(self):
        fields = [int(v) for v in self._read("/proc/stat").split("\n")[0].split()[1:9]]
        idle, total = fields[3] + fields[4], sum(fields)
        prev, self.cpu_prev = self.cpu_prev, (idle, total)
        if prev is None or total == prev[1]:
            return None
        return 1 - (idle - prev[0]) / (total - prev[1])

    def _memory(self):
        info = {}
        for line in self._read("/proc/meminfo").split("\n"):
            name, _, rest = line.partition(":")
            if name in ("MemTotal", "MemAvailable"):
                info[name] = int(rest.split()[0])
        return 1 - info["MemAvailable"] / info["MemTotal"]

    def _temperature(self):
        best = None
        for name in sorted(os.listdir("/sys/class/thermal"))[:32]:
            if name.startswith("thermal_zone"):
                try:
                    value = int(self._read("/sys/class/thermal/%s/temp" % name)) / 1000
                except (OSError, ValueError):
                    continue
                if 0 < value < 150 and (best is None or value > best):
                    best = value
        return best

    def sample(self):
        rows = []
        errors = (OSError, ValueError, KeyError, IndexError, ZeroDivisionError, AttributeError)
        try:
            cpu = self._cpu()
            if cpu is not None:
                rows.append(("CPU", "%d%%" % round(cpu * 100), cpu))
        except errors:
            pass
        try:
            mem = self._memory()
            rows.append(("MEM", "%d%%" % round(mem * 100), mem))
        except errors:
            pass
        try:
            usage = shutil.disk_usage("/")
            disk = usage.used / usage.total
            rows.append(("DISK", "%d%%" % round(disk * 100), disk))
        except errors:
            pass
        try:
            temp = self._temperature()
            if temp is not None:
                rows.append(("TEMP", "%dC" % round(temp), (temp - 30) / 65))
        except errors:
            pass
        try:
            load = os.getloadavg()[0]
            rows.append(("LOAD", ("%.2f" if load < 10 else "%.1f") % load,
                         load / (os.cpu_count() or 1)))
        except errors:
            pass
        return rows


def too_small(w, h):
    lines = [" " * w for _ in range(h)]
    if h:
        lines[h // 2] = "terminal too small"[:w].center(w)
    return lines


# ---------------------------------------------------------------------------
# Pixel style
# ---------------------------------------------------------------------------

UPPER = "▀"
LOWER = "▄"
FULL = "█"

WATER_STOPS = [(0.0, 0x2F9FD6), (0.35, 0x1670B0), (0.7, 0x0B3F78), (1.0, 0x062449)]
RAY = 0xA8E4FF
HAZE = 0x0F4D86  # distant things fade toward this colour
WHITE = 0xFFFFFF
N_LEVELS = 6
# Marks a colour that gives off its own light, so night does not dim it.
EMISSIVE = 0x1000000
RGB = 0xFFFFFF
SPARK = 0x7FFFD4 | EMISSIVE
TEXT = 0xD8F4FF | EMISSIVE
GOOD, WARN, BAD = 0x5FE08A | EMISSIVE, 0xF5D020 | EMISSIVE, 0xFF5A4A | EMISSIVE
TRACK = 0x2F628A

# Palette loaded into the Linux console, which has 16 colours and only
# allows the first 8 as a background.
C16 = [0x041830, 0x0A3A66, 0x1265A0, 0x2A8CC8, 0x6EC4EE, 0x968C6C, 0x1F7A3A, 0x5A6470,
       0xF57A1E, 0xF5F5F0, 0xF5D020, 0x1F5FD8, 0x101418, 0xE03030, 0x5FD070, 0xD8C8A0]


def mix(a, b, t):
    ar, ag, ab = a >> 16, (a >> 8) & 255, a & 255
    br, bg, bb = b >> 16, (b >> 8) & 255, b & 255
    return ((int(ar + (br - ar) * t) << 16) | (int(ag + (bg - ag) * t) << 8)
            | int(ab + (bb - ab) * t))


def _pack(colour, factor=1.0):
    r, g, b = colour
    r = min(255, max(0, int(r * factor)))
    g = min(255, max(0, int(g * factor)))
    b = min(255, max(0, int(b * factor)))
    return (r << 16) | (g << 8) | b


def water_colour(depth, stops=WATER_STOPS):
    for (d0, c0), (d1, c1) in zip(stops, stops[1:]):
        if depth <= d1:
            return mix(c0, c1, (depth - d0) / (d1 - d0))
    return stops[-1][1]


# Fish colours. Each function gets the part ("body", "tail" or "fin"), the
# position along that part (0 to 1) and the height across it (-1 top, 1 bottom).

def _clown(part, s, v):
    orange, white, black = (245, 122, 30), (250, 246, 236), (26, 20, 20)
    if part == "body":
        for centre, half in ((0.2, 0.05), (0.5, 0.055), (0.78, 0.07)):
            d = abs(s - centre)
            if d < half:
                return white
            if d < half + 0.04:
                return black
        return orange
    if part == "tail":
        return black if s < 0.2 else orange
    return (214, 96, 20)


def _tang(part, s, v):
    blue, dark, yellow = (36, 98, 222), (12, 22, 58), (245, 208, 32)
    if part == "body":
        if -0.78 < v < -0.18 and 0.1 < s < 0.8:
            return dark
        if s < 0.1:
            return dark
        return blue
    if part == "tail":
        return dark if abs(v) > 0.72 else yellow
    return (24, 70, 170)


def _angel(part, s, v):
    silver, black = (216, 216, 202), (32, 32, 38)
    if part == "body":
        for centre in (0.3, 0.55, 0.8):
            if abs(s - centre) < 0.05:
                return black
        return silver
    if part == "tail":
        return (196, 198, 188)
    return (188, 186, 160)


def _gold(part, s, v):
    if part == "body":
        return (248 + 6 * s, 140 + 50 * s, 20 + 30 * s)
    fade = 1 - s if part == "tail" else 0.3
    return (255, 165 + 50 * fade, 60 + 90 * fade)


def _tetra(part, s, v):
    if part == "body":
        if -0.4 < v < 0.05:
            return (60, 225, 255)
        if v >= 0.05 and s < 0.55:
            return (226, 50, 50)
        return (186, 198, 210)
    return (200, 212, 224)


def _shark(part, s, v):
    if part == "body":
        return (226, 232, 238) if v > 0.3 else (120, 134, 150)
    if part == "tail":
        return (104, 118, 134)
    return (94, 108, 124)


def _butterfly(part, s, v):
    yellow, white, black = (250, 212, 40), (246, 244, 232), (24, 22, 26)
    if part == "body":
        if 0.8 < s < 0.89:
            return black
        return yellow if s < 0.4 or v < -0.6 else white
    if part == "tail":
        return yellow
    return (236, 190, 30)


def _sardine(part, s, v):
    if part == "body":
        return (70, 110, 150) if v < -0.2 else (208, 220, 230)
    return (150, 170, 190)


def _angler(part, s, v):
    if part == "body":
        return (100, 74, 62) if v > 0.4 else (76, 54, 46)
    if part == "tail":
        return (62, 44, 38)
    return (54, 40, 36)


def _lantern(part, s, v):
    if part == "body":
        return (92, 112, 142) if v > 0.3 else (42, 62, 98)
    return (60, 80, 112)


# A fourth value marks a pixel that glows.
LIGHT = (130, 255, 230, 1)

TURTLE = [
    ["........gggggg........",
     "......ggGgGgGggg......",
     ".....gGgGGgGGgGgg..yy.",
     "....ggGGgGGgGGgGggyyky",
     "..yyyggggggggggggyyyyy",
     ".y...YYYYYYYYYYYY.....",
     ".......yyy....yy......",
     "......yyy......yy.....",
     ".....yy..............."],
    ["........gggggg........",
     "......ggGgGgGggg......",
     ".....gGgGGgGGgGgg..yy.",
     "....ggGGgGGgGGgGggyyky",
     "..yyyggggggggggggyyyyy",
     ".y...YYYYYYYYYYYY.....",
     "..........yyyy..yy....",
     "............yyy..y....",
     "......................"],
]

# len: body length in pixels for the nearest layer. aspect: body height over
# body length. tail: share of the length taken by the tail fin. tail_h: tail
# height against the body. fork: depth of the tail notch. dorsal and anal:
# (height, start, end) of the fins along the body.
SPECIES = {
    "clown": dict(colour=_clown, len=(15, 21), aspect=0.5, tail=0.22, tail_h=0.85,
                  fork=0.0, e=0.8, nose=7, dorsal=(0.3, 0.15, 0.75),
                  anal=(0.25, 0.2, 0.55), speed=(5, 9)),
    "tang": dict(colour=_tang, len=(16, 24), aspect=0.58, tail=0.2, tail_h=0.8,
                 fork=0.35, e=0.75, nose=6, dorsal=(0.22, 0.1, 0.85),
                 anal=(0.2, 0.1, 0.6), speed=(6, 10)),
    "angel": dict(colour=_angel, len=(13, 18), aspect=1.0, tail=0.24, tail_h=0.6,
                  fork=0.25, e=0.8, nose=6, dorsal=(0.9, 0.15, 0.7),
                  anal=(0.9, 0.2, 0.7), speed=(3, 6)),
    "gold": dict(colour=_gold, len=(16, 24), aspect=0.52, tail=0.34, tail_h=1.3,
                 fork=0.5, e=0.72, nose=6, dorsal=(0.42, 0.2, 0.7),
                 anal=(0.3, 0.2, 0.5), speed=(4, 7)),
    "tetra": dict(colour=_tetra, len=(7, 10), aspect=0.42, tail=0.26, tail_h=0.9,
                  fork=0.5, e=0.8, nose=7, dorsal=(0.35, 0.35, 0.65),
                  anal=(0.3, 0.3, 0.55), speed=(9, 14), school=True),
    "shark": dict(colour=_shark, len=(44, 56), aspect=0.3, tail=0.2, tail_h=1.5,
                  fork=0.7, e=0.72, nose=3, dorsal=(0.95, 0.4, 0.62),
                  anal=(0.45, 0.5, 0.66), speed=(6, 8), solo=True),
    "butterfly": dict(colour=_butterfly, len=(12, 17), aspect=0.82, tail=0.2, tail_h=0.6,
                      fork=0.0, e=0.85, nose=5, dorsal=(0.3, 0.1, 0.8),
                      anal=(0.3, 0.15, 0.7), speed=(4, 7)),
    "sardine": dict(colour=_sardine, len=(9, 13), aspect=0.3, tail=0.24, tail_h=1.0,
                    fork=0.6, e=0.8, nose=5, dorsal=(0.4, 0.4, 0.6),
                    anal=(0.3, 0.3, 0.5), speed=(10, 15), school=True),
    "angler": dict(colour=_angler, len=(16, 22), aspect=0.8, tail=0.2, tail_h=0.7,
                   fork=0.0, e=1.3, nose=9, dorsal=(0.2, 0.1, 0.5),
                   anal=(0.2, 0.15, 0.45), speed=(2, 4)),
    "lantern": dict(colour=_lantern, len=(8, 11), aspect=0.38, tail=0.26, tail_h=0.9,
                    fork=0.5, e=0.8, nose=7, dorsal=(0.35, 0.35, 0.65),
                    anal=(0.3, 0.3, 0.55), speed=(6, 10), school=True,
                    lights=((0.25, 0.5), (0.5, 0.5), (0.72, 0.5))),
    # Drawn by hand, so it has no body measurements.
    "turtle": dict(art=[TURTLE[0], TURTLE[0], TURTLE[1], TURTLE[1]], len=(22, 22),
                   speed=(3, 5), solo=True),
}

# What changes from one scene to the next: the water, the bottom, what grows
# there and which fish live in it. c16 holds the eight background colours for
# the Linux console: four water tones from deep to shallow, a highlight, sand,
# plants and rock.
SCENES = {
    "reef": dict(
        water=WATER_STOPS, ray=RAY, rays=0.42, haze=HAZE, surface=(0x9ADBF7, 0xE2F8FF),
        sand=mix(0xC9AE74, 0x0B3F78, 0.22), rocks=(0x70757D, 0x7A6C5C, 0x5E6670), rock_gap=45,
        plants=((0x1E8A3C, 0x7BD65A), (0x14703A, 0x4FBF6A), (0x2C9A54, 0xB6E36A)),
        accent=(0x7A2438, 0xD0566A), plant_h=(0.18, 0.5), plant_gap=(7, 16), blades=(2, 6),
        corals=60, fish=dict(clown=4, tang=3, angel=2, gold=3, tetra=3), shark=0.06,
        c16=C16[:8]),
    "lagoon": dict(
        water=[(0.0, 0x86E8E0), (0.35, 0x40C6CE), (0.7, 0x1F9AB6), (1.0, 0x157290)],
        ray=0xF4FFF0, rays=0.5, haze=0x2C9FB4, surface=(0xC4F6F2, 0xFFFFFF),
        sand=0xE2D4A8, rocks=(0x8A8C88, 0x9A8C78), rock_gap=90,
        plants=((0x1E9A50, 0x8CE070), (0x2CA868, 0xC0EE80)),
        accent=(0xC84870, 0xFF9AB0), plant_h=(0.1, 0.28), plant_gap=(12, 24), blades=(2, 5),
        corals=20, fish=dict(clown=4, tang=3, angel=2, butterfly=4, tetra=2, turtle=1),
        shark=0.0,
        c16=[0x157290, 0x1F9AB6, 0x40C6CE, 0x86E8E0, 0xD8FAF6, 0xD6C8A0, 0x1F8A4A, 0x6A7480]),
    "kelp": dict(
        water=[(0.0, 0x5CBC9C), (0.35, 0x2C8672), (0.7, 0x14504A), (1.0, 0x082A2C)],
        ray=0xDCF8B4, rays=0.5, haze=0x1C6458, surface=(0xA8E6C8, 0xE6FFF0),
        sand=0x8E8260, rocks=(0x5E665E, 0x6E6654, 0x4E5650), rock_gap=24,
        plants=((0x4A5A14, 0xA8B83C), (0x3C5218, 0x8FA834), (0x5A6418, 0xC8C050)),
        accent=(0x2C7A3C, 0x7BD65A), plant_h=(0.55, 0.95), plant_gap=(6, 13), blades=(1, 3),
        leafy=True, corals=0, fish=dict(gold=4, sardine=4, tang=1), shark=0.08,
        c16=[0x082A2C, 0x14504A, 0x2C8672, 0x5CBC9C, 0xB8ECCC, 0x8A7C58, 0x5A7A1E, 0x565E58]),
    "deep": dict(
        water=[(0.0, 0x0A1C3A), (0.4, 0x061226), (1.0, 0x02060F)],
        ray=0x2A4A7A, rays=0.0, haze=0x040C1C, surface=None,
        sand=0x3E3E4A, rocks=(0x30343E, 0x3A3640, 0x282C36), rock_gap=28,
        plants=((0xB8B0A8, 0xC02828),),
        accent=(0xB8B0A8, 0xE04040), plant_h=(0.06, 0.16), plant_gap=(14, 30), blades=(2, 5),
        corals=0, fish=dict(angler=2, lantern=4), shark=0.0, jellies=True, glow=True,
        c16=[0x02060F, 0x061226, 0x0A1C3A, 0x16305A, 0x3A5A8A, 0x44444F, 0x6A1C24, 0x2A2E38]),
}
SCENE_NAMES = list(SCENES)
CORALS = ((0xD84A6A, 0xFFB0C0), (0xE8703A, 0xFFD08A), (0x8A4AC8, 0xD8B0FF),
          (0xE8C83A, 0xFFF0A0))
JELLY = (0xFF7AC8, 0x7ADFFF, 0xB48AFF, 0x8AFFC8)
LURE = 0xFFF0A0 | EMISSIVE

TAIL_FRAMES = (1.0, 0.88, 0.7, 0.88)
LAYER_SCALE = (0.6, 0.8, 1.0)
LAYER_HAZE = (0.42, 0.2, 0.0)
_SPRITES = {}


def _draw_fish(spec, length, squeeze):
    """Returns a grid of (r, g, b) or None for one fish facing right."""
    colour = spec["colour"]
    tail_w = spec["tail"] * length
    body_w = length - tail_w
    half = max(1.4, body_w * spec["aspect"] / 2)
    dorsal_h, d0, d1 = spec["dorsal"]
    anal_h, a0, a1 = spec["anal"]
    tail_h, fork, e, nose = spec["tail_h"], spec["fork"], spec["e"], spec["nose"]
    top = int(math.ceil(half * max(1 + dorsal_h, tail_h)))
    bottom = int(math.ceil(half * max(1 + anal_h, tail_h)))
    start = tail_w * (1 - squeeze)

    grid = []
    for py in range(top + bottom):
        vy = (py + 0.5 - top) / half
        a = abs(vy)
        row = []
        for px in range(length):
            xs = px + 0.5
            c = None
            if xs < tail_w:
                if xs >= start:
                    tu = (xs - start) / (tail_w * squeeze)
                    outer = tail_h * (1 - 0.78 * tu ** 1.2)
                    notch = 0.0
                    if fork:
                        if tu < 0.6:
                            notch = fork * tail_h * (1 - tu / 0.6)
                    else:
                        outer *= min(1.0, tu * 4 + 0.4)
                    if notch <= a <= outer:
                        r, g, b = colour("tail", tu, vy / tail_h)
                        f = 0.82 + 0.22 * tu
                        c = (r * f, g * f, b * f)
            else:
                s = (xs - tail_w) / body_w
                th = 0.2 + 0.8 * max(0.0, math.sin(math.pi * s ** e)) ** 0.9
                th *= min(1.0, (1 - s) * nose) ** 0.5
                if a <= th:
                    v = vy / th
                    f = 0.8 + 0.16 * (v + 1)
                    if -0.55 < v < -0.2:
                        f *= 1.12
                    if abs(v) > 0.86:
                        f *= 0.8
                    r, g, b = colour("body", s, v)
                    c = (r * f, g * f, b * f)
                elif vy < 0 and d0 < s < d1:
                    if a <= th + dorsal_h * math.sin(math.pi * (s - d0) / (d1 - d0)) ** 0.6:
                        r, g, b = colour("fin", s, -1.0)
                        c = (r * 0.9, g * 0.9, b * 0.9)
                elif vy > 0 and a0 < s < a1:
                    if a <= th + anal_h * math.sin(math.pi * (s - a0) / (a1 - a0)) ** 0.6:
                        r, g, b = colour("fin", s, 1.0)
                        c = (r * 0.8, g * 0.8, b * 0.8)
            row.append(c)
        grid.append(row)

    # Gill line, then the eye.
    if length >= 18:
        gx = int(tail_w + 0.68 * body_w)
        for py in range(top - int(half * 0.45), top + int(half * 0.5)):
            c = grid[py][gx]
            if c:
                grid[py][gx] = (c[0] * 0.8, c[1] * 0.8, c[2] * 0.8)
    ex = min(length - 1, int(tail_w + 0.84 * body_w))
    ey = max(0, top - 1 - int(half * 0.22))
    if grid[ey][ex]:
        grid[ey][ex] = (14, 14, 20)
        if length >= 12 and ex and grid[ey][ex - 1]:
            grid[ey][ex - 1] = (245, 245, 240)
        if length >= 22 and ey and grid[ey - 1][ex]:
            grid[ey - 1][ex] = (245, 245, 240)
    for along, down in spec.get("lights", ()):
        px, py = int(tail_w + along * body_w), top + int(down * half * 0.6)
        if py < len(grid) and grid[py][px]:
            grid[py][px] = LIGHT
    return grid


def _spans(grid, haze, colour=HAZE):
    out = []
    for row in grid:
        spans = []
        x, n = 0, len(row)
        while x < n:
            if row[x] is None:
                x += 1
                continue
            x0 = x
            while x < n and row[x] is not None:
                x += 1
            spans.append((x0, [mix(_pack(c[:3]), colour, haze) | (EMISSIVE if len(c) > 3 else 0)
                               for c in row[x0:x]]))
        out.append(spans)
    return out


def fish_sprites(name, length, layer, colour=HAZE):
    """Returns (right frames, left frames, width, height), cached."""
    key = (name, length, layer, colour)
    if key not in _SPRITES:
        spec = SPECIES[name]
        if "art" in spec:
            grids = [[[PALETTE.get(ch) for ch in line] for line in art] for art in spec["art"]]
        else:
            grids = [_draw_fish(spec, length, squeeze) for squeeze in TAIL_FRAMES]
        haze = LAYER_HAZE[layer]
        right = [_spans(grid, haze, colour) for grid in grids]
        left = [_spans([row[::-1] for row in grid], haze, colour) for grid in grids]
        _SPRITES[key] = (right, left, len(grids[0][0]), len(grids[0]))
    return _SPRITES[key]


def blit(rows, sprite, x, y, w, h):
    for dy, spans in enumerate(sprite):
        yy = y + dy
        if 0 <= yy < h:
            row = rows[yy]
            for x0, cols in spans:
                xx = x + x0
                n = len(cols)
                if xx >= w or xx + n <= 0:
                    continue
                if xx < 0:
                    cols = cols[-xx:]
                    xx = 0
                if xx + len(cols) > w:
                    cols = cols[:w - xx]
                row[xx:xx + len(cols)] = cols


# Shells and small animals on the sand, drawn with the letters of PALETTE.
PALETTE = {
    "p": (232, 184, 192), "P": (248, 224, 224),
    "c": (216, 192, 144), "C": (244, 230, 192),
    "w": (240, 240, 232),
    "o": (232, 96, 58), "O": (245, 154, 106),
    "u": (74, 42, 106), "U": (122, 74, 160),
    "r": (168, 44, 32), "R": (216, 64, 44), "k": (16, 16, 20),
    "s": (176, 122, 58), "S": (224, 176, 96), "b": (216, 200, 160),
    "g": (46, 110, 70), "G": (104, 166, 92), "y": (150, 160, 90), "Y": (214, 206, 150),
}
SHELLS = [
    [".pPp.", "pPpPp", "pPpPp", ".ppp."],              # scallop
    [".cc..", "cCCc.", ".cccc"],                       # conch
    ["www", ".w."],                                    # clam
    ["..o..", "ooOoo", ".oOo.", ".o.o.", "o...o"],     # starfish
    ["u.u.u", ".uUu.", "uUUUu", ".uuu."],              # urchin
]
CRITTER_ART = {
    "crab": (3.0, [["r.......r", "rr.k.k.rr", ".rRRRRRr.", "..RRRRR..", ".r.r.r.r."],
                   ["r.......r", "rr.k.k.rr", ".rRRRRRr.", "..RRRRR..", "r.r...r.r"]]),
    "snail": (0.5, [["..ss...", ".sSSs.k", ".sSss.b", "bbbbbbb"]]),
}


def _critter(frames):
    grids = [[[PALETTE.get(ch) for ch in line] for line in art] for art in frames]
    right = [_spans(grid, 0.1) for grid in grids]
    left = [_spans([row[::-1] for row in grid], 0.1) for grid in grids]
    return right, left, len(frames[0][0]), len(frames[0])


CRITTERS = {name: (speed,) + _critter(frames) for name, (speed, frames) in CRITTER_ART.items()}

# Three by five pixel letters for the date and the system monitor.
FONT = {ch: rows.split("/") for ch, rows in {
    "A": ".#./#.#/###/#.#/#.#", "B": "##./#.#/##./#.#/##.", "C": ".##/#../#../#../.##",
    "D": "##./#.#/#.#/#.#/##.", "E": "###/#../##./#../###", "F": "###/#../##./#../#..",
    "G": ".##/#../#.#/#.#/.##", "H": "#.#/#.#/###/#.#/#.#", "I": "###/.#./.#./.#./###",
    "J": "..#/..#/..#/#.#/.#.", "K": "#.#/#.#/##./#.#/#.#", "L": "#../#../#../#../###",
    "M": "#.#/###/###/#.#/#.#", "N": "##./#.#/#.#/#.#/#.#", "O": ".#./#.#/#.#/#.#/.#.",
    "P": "##./#.#/##./#../#..", "Q": ".#./#.#/#.#/###/.##", "R": "##./#.#/##./#.#/#.#",
    "S": ".##/#../.#./..#/##.", "T": "###/.#./.#./.#./.#.", "U": "#.#/#.#/#.#/#.#/###",
    "V": "#.#/#.#/#.#/#.#/.#.", "W": "#.#/#.#/###/###/#.#", "X": "#.#/#.#/.#./#.#/#.#",
    "Y": "#.#/#.#/.#./.#./.#.", "Z": "###/..#/.#./#../###",
    "0": "###/#.#/#.#/#.#/###", "1": ".#./##./.#./.#./###", "2": "###/..#/###/#../###",
    "3": "###/..#/###/..#/###", "4": "#.#/#.#/###/..#/..#", "5": "###/#../###/..#/###",
    "6": "###/#../###/#.#/###", "7": "###/..#/..#/..#/..#", "8": "###/#.#/###/#.#/###",
    "9": "###/#.#/###/..#/###", "%": "#.#/..#/.#./#../#.#", ".": ".../.../.../.../.#.",
    ":": ".../.#./.../.#./...", "/": "..#/..#/.#./#../#..", "-": ".../.../###/.../...",
}.items()}


class Swimmer:
    __slots__ = ("name", "layer", "right", "left", "w", "h", "x", "y", "dir",
                 "speed", "phase", "target_y", "retarget", "members", "trail")


SEGMENTS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
            "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abfgcd"}
# Seven segment bars as (x, y, width, height) in units of the bar thickness.
BARS = {"a": (0, 0, 4, 1), "g": (0, 3, 4, 1), "d": (0, 6, 4, 1), "f": (0, 0, 1, 4),
        "b": (3, 0, 1, 4), "e": (0, 3, 1, 4), "c": (3, 3, 1, 4)}


class PixelTank:
    style = "pixel"

    def __init__(self, n_fish, rng, scene="reef"):
        self.rng = rng
        self.scene = scene
        self.n_fish = n_fish
        self.w = self.h = self.ph = 0
        self.t = 0.0
        self.fish = []
        self.bubbles = []
        self.flakes = []

    def resize(self, w, h):
        rng = self.rng
        self.w, self.h = w, h
        ph = self.ph = h * 2
        self.fish, self.bubbles, self.flakes = [], [], []
        self.glow = {}
        self.lit_colours = set()
        self.dark = {}
        self.tint = {}
        self.critters = []
        self.sparks = []
        self.jellies = []
        self.clock_u = self.clock_max = 0
        sc = self.sc = SCENES[self.scene]
        self.c16 = sc["c16"] + C16[8:]
        haze = sc["haze"]
        if w < MIN_W or h < MIN_H:
            return

        self.pal = []
        for y in range(ph):
            d = y / (ph - 1)
            base = water_colour(d, sc["water"])
            strength = sc["rays"] * (1 - d) ** 1.4
            self.pal.append([mix(base, sc["ray"], i / (N_LEVELS - 1) * strength)
                             for i in range(N_LEVELS)])
        self.slant = ph // 2
        self.levels = b""
        self.levels_at = -1.0

        sand_h = max(4, ph // 7)
        p1, p2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
        self.dune = []
        for x in range(w):
            bump = 1.6 * math.sin(x * 0.07 + p1) + 1.1 * math.sin(x * 0.023 + p2)
            self.dune.append(min(ph - 2, ph - sand_h + int(round(bump))))
        self.floor = min(self.dune)

        grid = [dict() for _ in range(ph)]
        sand = sc["sand"]
        for x in range(w):
            top = self.dune[x]
            for y in range(top, ph):
                depth = y - top
                f = 1.12 if depth == 0 else 1 - 0.04 * min(depth, 6)
                grid[y][x] = mix(0, sand, min(1.0, f * rng.uniform(0.9, 1.04)))
            if rng.random() < 0.06 and top + 1 < ph:
                grid[top + 1][x] = mix(sand, 0x1A1410, 0.55)

        for _ in range(max(1, w // sc["rock_gap"])):
            cx = rng.randrange(4, w - 4)
            radius = rng.randint(4, max(5, min(14, w // 12)))
            height = radius * rng.uniform(0.6, 1.0)
            tone = rng.choice(sc["rocks"])
            for dx in range(-radius, radius + 1):
                x = cx + dx
                if not 0 <= x < w:
                    continue
                col_h = int(height * math.sqrt(1 - (dx / radius) ** 2) * rng.uniform(0.85, 1.1))
                for k in range(col_h):
                    y = self.dune[x] + 1 - k
                    if 0 <= y < ph:
                        light = 0.62 + 0.5 * k / max(1, col_h) - 0.14 * dx / radius
                        light *= rng.uniform(0.92, 1.06)
                        grid[y][x] = mix(mix(0, tone, min(1.0, light)), haze, 0.15)

        if sc["corals"]:
            for _ in range(max(1, w // sc["corals"])):
                self._coral(grid, rng.randrange(3, w - 3))

        for _ in range(max(2, w // 14)):
            art = rng.choice(SHELLS)
            x0 = rng.randrange(1, max(2, w - 6))
            base = self.dune[min(w - 1, x0 + len(art[0]) // 2)]
            for dy, line in enumerate(art):
                y = base - len(art) + 1 + dy
                for dx, ch in enumerate(line):
                    c = PALETTE.get(ch)
                    if c and x0 + dx < w and 0 <= y < ph:
                        grid[y][x0 + dx] = mix(_pack(c), haze, 0.12)

        self.static = []
        for cells in grid:
            spans = []
            xs = sorted(cells)
            i = 0
            while i < len(xs):
                j = i
                while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
                    j += 1
                spans.append((xs[i], [cells[x] for x in xs[i:j + 1]]))
                i = j + 1
            self.static.append(spans)

        self.leafy = sc.get("leafy", False)
        self.plants = []
        x = rng.randint(2, 8)
        while x < w - 2:
            base, tip = sc["accent"] if rng.random() < 0.15 else rng.choice(sc["plants"])
            front = rng.random() < 0.3
            tallest = max(4, min(self.floor - 5, int(ph * rng.uniform(*sc["plant_h"]))))
            blades = []
            for _ in range(rng.randint(*sc["blades"])):
                bx = min(w - 1, max(0, x + rng.randint(-2, 2)))
                height = max(3, int(tallest * rng.uniform(0.5, 1.0)))
                cols = [mix(mix(base, tip, i / height), haze, 0.0 if front else 0.4)
                        for i in range(height)]
                blades.append((bx, self.dune[bx], height, rng.uniform(0, 6.28),
                               rng.uniform(1.5, 4.0) * height / 20,
                               rng.uniform(-0.15, 0.15), cols))
            self.plants.append((front, blades))
            x += rng.randint(*sc["plant_gap"])

        self.stones = [rng.randrange(3, w - 3) for _ in range(1 + w // 80)]
        for name, n in (("crab", 1 + w // 120), ("snail", 1 + w // 160)):
            for _ in range(n):
                self.critters.append([name, rng.uniform(2, w - 12), rng.choice((-1, 1)), 0.0])
        self.sparks = [(rng.randrange(w), rng.randrange(5, self.floor), rng.uniform(0, 6.28))
                       for _ in range(w * ph // 350)]
        if sc.get("jellies"):
            for _ in range(2 + w // 45):
                r = rng.randint(3, max(3, min(6, ph // 12)))
                self.jellies.append([rng.uniform(r, w - r),
                                     rng.uniform(6, max(7, self.floor - 4 * r)), r,
                                     rng.uniform(0, 6.28), rng.choice(JELLY),
                                     rng.uniform(-1.2, 1.2), True])
        count = self.n_fish
        if count is None:
            count = max(3, min(18, w * ph // 900))
        self.set_fish(count, scatter=True)

    def _coral(self, grid, cx):
        """Grows a branching coral up from the sand."""
        rng, w, ph = self.rng, self.w, self.ph
        base, tip = rng.choice(CORALS)
        foot = self.dune[cx]
        height = rng.randint(6, max(7, min(16, ph // 5)))
        arms = [(float(cx), foot, 0.0, height)]
        grown = 0
        while arms:
            x, y, lean, n = arms.pop()
            for i in range(n):
                yy = y - i
                colour = mix(mix(base, tip, min(1.0, (foot - yy) / height)),
                             self.sc["haze"], 0.12)
                for xx in (int(x + 0.5), int(x + 0.5) + (1 if n - i > 2 else 0)):
                    if 0 <= xx < w and 0 <= yy < ph:
                        grid[yy][xx] = colour
                x += lean
                if i >= 2 and n - i > 3 and grown < 10 and rng.random() < 0.3:
                    grown += 1
                    arms.append((x, yy, lean + rng.choice((-0.6, 0.6)),
                                 int((n - i) * rng.uniform(0.6, 0.9))))

    def set_fish(self, count, scatter=False):
        count = max(0, min(MAX_FISH, count))
        del self.fish[count:]
        while len(self.fish) < count:
            fish = self._new_fish(scatter)
            if fish is None:
                break
            self.fish.append(fish)

    def _new_fish(self, scatter=False):
        if self.w < MIN_W or self.h < MIN_H:
            return None
        rng = self.rng
        names = list(self.sc["fish"])
        weights = list(self.sc["fish"].values())
        shark_ok = not scatter and self.ph >= 44 and self.w >= 90
        for _ in range(8):
            if shark_ok and rng.random() < self.sc["shark"]:
                name = "shark"
            else:
                name = rng.choices(names, weights)[0]
            spec = SPECIES[name]
            solo = spec.get("solo")
            if solo and any(f.name == name for f in self.fish):
                continue
            layer = 2 if solo else rng.choice((0, 1, 1, 2, 2))
            length = max(6, int(rng.randint(*spec["len"]) * LAYER_SCALE[layer]))
            right, left, w, h = fish_sprites(name, length, layer, self.sc["haze"])
            if h <= self.floor - 8 and w <= self.w * 0.6:
                break
        else:
            return None

        f = Swimmer()
        f.name, f.layer, f.right, f.left, f.w, f.h = name, layer, right, left, w, h
        f.dir = rng.choice((-1, 1))
        f.speed = rng.uniform(*spec["speed"]) * LAYER_SCALE[layer]
        f.phase = rng.uniform(0, 4)
        f.y = rng.uniform(4, self.floor - h - 2)
        f.target_y = f.y
        f.retarget = rng.uniform(1, 5)
        f.members = [(0.0, 0.0, 0.0)]
        if spec.get("school"):
            for _ in range(rng.randint(4, 8)):
                f.members.append((rng.uniform(2, 3.5 * w), rng.uniform(-1.6 * h, 1.6 * h),
                                  rng.uniform(0, 6.28)))
        f.trail = max(m[0] for m in f.members)
        if scatter:
            f.x = rng.uniform(0, self.w - w)
        else:
            f.x = float(-w if f.dir > 0 else self.w)
        return f

    def feed(self):
        if self.w < MIN_W or self.h < MIN_H:
            return
        rng = self.rng
        centre = rng.uniform(self.w * 0.15, self.w * 0.85)
        for _ in range(rng.randint(6, 10)):
            if len(self.flakes) < 60:
                self.flakes.append([centre + rng.uniform(-8, 8), rng.uniform(3, 6),
                                    rng.uniform(2.0, 4.0), rng.uniform(0, 6.28), 0.0])

    def _bubble(self, x, y):
        if len(self.bubbles) < MAX_BUBBLES:
            rng = self.rng
            self.bubbles.append([x, y, rng.uniform(6, 12), rng.uniform(0, 6.28),
                                 2 if rng.random() < 0.3 else 1])

    def step(self, dt):
        if self.w < MIN_W or self.h < MIN_H:
            return
        rng = self.rng
        self.t += dt
        w, floor = self.w, self.floor

        alive = []
        for f in self.fish:
            single = len(f.members) == 1
            boost = 1.0
            mouth_x = f.x + f.w if f.dir > 0 else f.x
            mouth_y = f.y + f.h / 2
            if self.flakes and single and f.name != "shark":
                flake = min(self.flakes,
                            key=lambda k: abs(k[0] - mouth_x) + 2 * abs(k[1] - mouth_y))
                dx, dy = flake[0] - mouth_x, flake[1] - mouth_y
                if abs(dx) < 2.5 and abs(dy) < 2.5:
                    self.flakes.remove(flake)
                else:
                    if dx * f.dir < -3:
                        f.dir = -f.dir
                    f.target_y = flake[1] - f.h / 2
                    boost = 1.8
            else:
                f.retarget -= dt
                if f.retarget <= 0:
                    f.retarget = rng.uniform(3, 9)
                    f.target_y = rng.uniform(4, floor - f.h - 2)
                inside = 0 < f.x < w - f.w
                if single and inside and f.name != "shark" and rng.random() < 0.03 * dt:
                    f.dir = -f.dir

            f.x += f.dir * f.speed * boost * dt
            climb = max(-f.speed * 0.5, min(f.speed * 0.5, (f.target_y - f.y) * 0.8))
            f.y = max(3.0, min(floor - f.h - 1.0, f.y + climb * boost * dt))
            f.phase += dt * (2.5 + f.speed * 0.45 * boost)
            if rng.random() < 0.08 * dt:
                self._bubble(mouth_x, mouth_y)

            gone = f.x - f.trail > w + 2 if f.dir > 0 else f.x + f.w + f.trail < -2
            if gone:
                f = self._new_fish()
            if f is not None:
                alive.append(f)
        self.fish = alive

        for sx in self.stones:
            if rng.random() < 1.6 * dt:
                self._bubble(sx + rng.uniform(-1.5, 1.5), float(self.dune[sx]))
        for b in self.bubbles:
            b[1] -= b[2] * dt
        self.bubbles = [b for b in self.bubbles if b[1] >= 3]

        for c in self.critters:
            speed, _r, _l, cw, _ch = CRITTERS[c[0]]
            if c[3] > 0:
                c[3] -= dt
            else:
                c[1] += c[2] * speed * dt
                if rng.random() < 0.15 * dt:
                    c[3] = rng.uniform(1, 4)
                if rng.random() < 0.05 * dt:
                    c[2] = -c[2]
            if c[1] < 1:
                c[1], c[2] = 1.0, 1
            elif c[1] > w - cw - 1:
                c[1], c[2] = float(w - cw - 1), -1

        for j in self.jellies:
            # A jellyfish climbs in pulses, then sinks for a while.
            j[3] += dt * 1.8
            if j[6]:
                j[1] -= (2.6 * max(0.0, math.sin(j[3])) - 0.4) * dt
            else:
                j[1] += 0.6 * dt
            j[0] += j[5] * dt
            if j[1] < 5:
                j[6] = False
            elif j[1] > floor - 4 * j[2]:
                j[6] = True
            if not j[2] < j[0] < w - j[2]:
                j[5] = -j[5]
                j[0] = max(float(j[2]), min(float(w - j[2]), j[0]))

        for k in self.flakes:
            x = min(w - 1, max(0, int(k[0])))
            if k[1] < self.dune[x] - 1:
                k[1] += k[2] * dt
            k[4] += dt
        self.flakes = [k for k in self.flakes if k[4] < 30]

    def _levels(self):
        t = self.t
        out = bytearray()
        for x in range(self.w + self.slant + 1):
            v = (math.sin(x * 0.11 + t * 0.35) + math.sin(x * 0.047 - t * 0.22 + 1.7)
                 + 0.6 * math.sin(x * 0.29 + t * 0.5 + 4.0))
            out.append(int(max(0.0, min(1.0, (v - 0.5) / 1.7)) * (N_LEVELS - 1) + 0.5))
        return bytes(out)

    def draw(self, state, now, hint, night=False):
        """Returns the pixel rows and {cell row: {cell column: character}}."""
        w, ph, t = self.w, self.ph, self.t
        if t - self.levels_at >= 0.4 or len(self.levels) != w + self.slant + 1:
            self.levels = self._levels()
            self.levels_at = t
        levels, slant, pal = self.levels, self.slant, self.pal
        rows = []
        for y in range(ph):
            start = slant - y // 2
            rows.append(list(map(pal[y].__getitem__, levels[start:start + w])))

        # Waves on the surface, seen from below. The deep sea has none.
        r0, r1, r2, r3 = rows[0], rows[1], rows[2], rows[3]
        mid, foam = self.sc["surface"] or (0, 0)
        for x in range(w if self.sc["surface"] else 0):
            crest = 1.6 + math.sin(x * 0.13 + t * 1.3) + 0.6 * math.sin(x * 0.31 - t * 1.9)
            r0[x] = mid
            if crest >= 1:
                r1[x] = mid if crest >= 2 else foam
                if crest >= 2:
                    r2[x] = mid if crest >= 3 else foam
                    if crest >= 3:
                        r3[x] = foam
            else:
                r0[x] = foam

        text = {}
        self._draw_plants(rows, False)
        # The clock goes over the far plants, so tall kelp does not hide it.
        y = max(6, int(ph * 0.08))
        if state.clock:
            y = self._draw_clock(rows, state, now)
        if state.date:
            self._draw_date(rows, now, y, bool(state.clock) and self.clock_u >= 4)

        for spans, row in zip(self.static, rows):
            for x0, cols in spans:
                row[x0:x0 + len(cols)] = cols
        for name, cx, direction, _pause in self.critters:
            _speed, right, left, cw, ch = CRITTERS[name]
            frames = right if direction > 0 else left
            foot = self.dune[min(w - 1, int(cx) + cw // 2)]
            blit(rows, frames[int(cx) % len(frames)], int(cx), foot - ch + 1, w, ph)

        for layer in (0, 1):
            self._draw_fish(rows, layer)
        self._draw_jellies(rows)
        self._draw_plants(rows, True)
        self._draw_fish(rows, 2)

        for bx, by, _vy, phase, size in self.bubbles:
            x = int(bx + math.sin(t * 3 + phase) * 1.2)
            y = int(by)
            if 0 <= x < w - 1 and 0 <= y < ph - 1:
                if size == 1:
                    rows[y][x] = 0xBFE8FF
                else:
                    rows[y][x] = 0xF0FBFF
                    rows[y][x + 1] = rows[y + 1][x] = 0x9AD4F2
                    rows[y + 1][x + 1] = 0x7FC3E8
        for fx, fy, _vy, phase, _age in self.flakes:
            x = int(fx + math.sin(t * 2 + phase) * 1.5)
            y = int(fy)
            if 0 <= x < w and 0 <= y < ph:
                rows[y][x] = 0xE8B04A if phase > 3 else 0xD0703A
        if night or self.sc.get("glow"):
            # Glowing plankton.
            for x, y, phase in self.sparks:
                if math.sin(t * 1.7 + phase) > 0.7:
                    rows[y][x] = SPARK

        if state.monitor and state.metrics:
            self._draw_monitor(rows, text, state.metrics)
        if state.paused:
            self._text(text, 1, 2, "[paused]")
        if hint:
            lines = hint_lines(w)
            for i, line in enumerate(lines):
                self._text(text, self.h - len(lines) + i, max(0, (w - len(line)) // 2), line)
        return rows, text

    @staticmethod
    def _text(text, cell_row, x, s):
        line = text.setdefault(cell_row, {})
        for i, ch in enumerate(s):
            if ch != " ":
                line[x + i] = ch

    def _draw_fish(self, rows, layer):
        w, ph, t, floor = self.w, self.ph, self.t, self.floor
        for f in self.fish:
            if f.layer != layer:
                continue
            frames = f.right if f.dir > 0 else f.left
            for ox, oy, phase in f.members:
                sprite = frames[int(f.phase + phase) % len(frames)]
                y = f.y + oy + (math.sin(t * 1.5 + phase) * 1.2 if phase else 0.0)
                y = max(3.0, min(floor - f.h - 1.0, y))
                blit(rows, sprite, math.floor(f.x - f.dir * ox), int(y), w, ph)
            if f.name == "angler":
                # The lure hangs on a stalk ahead of the head.
                nose = math.floor(f.x) + (f.w - 1 if f.dir > 0 else 0)
                top = int(max(3.0, min(floor - f.h - 1.0, f.y)))
                for back, colour in ((0, LURE), (1, 0x6A5044), (2, 0x6A5044)):
                    x = nose - f.dir * back
                    if 0 <= x < w:
                        rows[top + back][x] = colour

    def _draw_jellies(self, rows):
        w, t, floor, tint = self.w, self.t, self.floor, self.tint

        def put(x, y, colour, level):
            if 0 <= x < w and 3 <= y < floor:
                key = (rows[y][x], colour, level)
                c = tint.get(key)
                if c is None:
                    if len(tint) > 20000:
                        tint.clear()
                    c = tint[key] = mix(key[0] & RGB, colour, level) | EMISSIVE
                rows[y][x] = c

        for cx, cy, r, phase, colour, _drift, _rising in self.jellies:
            x0, y0 = int(cx), int(cy)
            squeeze = 1 - 0.18 * max(0.0, math.sin(phase))
            for dy in range(r):
                n = int(r * squeeze * math.sqrt(1 - ((r - dy - 0.5) / r) ** 2) + 0.5)
                for dx in range(-n, n + 1):
                    rim = dy == 0 or dy == r - 1 or abs(dx) == n
                    put(x0 + dx, y0 + dy, colour, 0.9 if rim else 0.45)
            for k in range(-r + 1, r, 2):
                length = 2 * r + k % 3
                for i in range(length):
                    wave = math.sin(t * 2 + phase + i * 0.7 + k) * 1.2 * i / length
                    put(x0 + k + int(round(wave)), y0 + r + i, colour,
                        0.6 if i < length // 2 else 0.3)

    def _draw_plants(self, rows, front):
        w, ph, t, leafy = self.w, self.ph, self.t, self.leafy
        for is_front, blades in self.plants:
            if is_front != front:
                continue
            for bx, by, height, phase, sway, lean, cols in blades:
                a = sway * math.sin(t * 1.1 + phase) + lean * height
                b = sway * 0.5 * math.sin(t * 1.7 + phase * 1.3)
                thick = height * 0.6
                for i in range(height):
                    y = by - i
                    if not 0 <= y < ph:
                        continue
                    f = i / height
                    x = int(bx + f * f * (a + b * f) + 0.5)
                    if 0 <= x < w:
                        rows[y][x] = cols[i]
                        if i < thick and x + 1 < w:
                            rows[y][x + 1] = cols[i]
                    if leafy and i % 4 == 1:
                        # Kelp leaves, one side then the other.
                        side = x + (2 if i % 8 == 1 else -1)
                        if 0 <= side < w:
                            rows[y][side] = cols[min(height - 1, i + height // 4)]

    def _glow_rect(self, rows, x, y, width, height, colour=None):
        """Lightens a rectangle of water, or fills it when a colour is given."""
        glow, lit_colours = self.glow, self.lit_colours
        for yy in range(max(0, y), min(self.ph, y + height)):
            row = rows[yy]
            for xx in range(max(0, x), min(self.w, x + width)):
                if colour is not None:
                    row[xx] = colour
                    continue
                c = row[xx]
                if c in lit_colours:
                    continue  # already lit, for example where two bars meet
                lit = glow.get(c)
                if lit is None:
                    lit = glow[c] = mix(c & RGB, WHITE, 0.62) | EMISSIVE
                    lit_colours.add(lit)
                row[xx] = lit

    def _glow_text(self, rows, x, y, s, scale):
        for ch in s:
            glyph = FONT.get(ch)
            if glyph:
                for r, line in enumerate(glyph):
                    for c, bit in enumerate(line):
                        if bit == "#":
                            self._glow_rect(rows, x + c * scale, y + r * scale, scale, scale)
            x += 4 * scale

    def _draw_clock(self, rows, state, now):
        """Draws the seven segment clock. Returns the pixel row below it."""
        w = self.w
        label, _date, suffix = clock_text(state, now)
        units = sum(5 if ch in SEGMENTS else 2 for ch in label) - 1
        y0 = max(6, int(self.ph * 0.08))
        top = max(1, min(8, (w - 4) // units, (self.floor - y0 - 4) // 7))
        auto = max(1, min(5, w // (units + 6), int(self.ph * 0.34) // 7))
        u = min(top, state.clock_size or auto)
        self.clock_u, self.clock_max = u, top

        x = (w - units * u) // 2
        for ch in label:
            if ch in SEGMENTS:
                bars = [BARS[seg] for seg in SEGMENTS[ch]]
                advance = 5
            else:
                bars = [(0, 2, 1, 1), (0, 4, 1, 1)] if ch == ":" else []
                advance = 2
            for bx, by, bw, bh in bars:
                self._glow_rect(rows, x + bx * u, y0 + by * u, bw * u, bh * u)
            x += advance * u
        if suffix:
            self._glow_text(rows, x + 1, y0, suffix.strip(), 2 if u >= 4 else 1)
        return y0 + 7 * u + max(2, u)

    def _draw_date(self, rows, now, y, big):
        s = "%s %d %s" % (DAYS[now.tm_wday].upper(), now.tm_mday,
                          MONTHS[now.tm_mon - 1].upper())
        scale = 2 if big else 1
        width = len(s) * 4 * scale - scale
        if width <= self.w - 2 and y + 5 * scale < self.floor:
            self._glow_text(rows, (self.w - width) // 2, y, s, scale)

    def _draw_monitor(self, rows, text, metrics):
        """A dark glass panel above the sand with one line per reading."""
        w = self.w
        first = (self.floor - 3) // 2 - len(metrics)  # top cell row of the panel
        if w < 40 or first < 4:
            line = "  ".join("%s %s" % (label, value) for label, value, _f in metrics)
            self._text(text, 2, 2, line[:max(0, w - 4)])
            return

        x0, width = 2, 23
        dark = self.dark
        for yy in range(2 * first - 1, 2 * (first + len(metrics)) + 1):
            row = rows[yy]
            for xx in range(x0 - 1, x0 + width):
                c = row[xx]
                shade = dark.get(c)
                if shade is None:
                    shade = dark[c] = mix(c & RGB, 0x02101F, 0.6)
                row[xx] = shade
        for i, (label, value, fraction) in enumerate(metrics):
            self._text(text, first + i, x0, label)
            self._text(text, first + i, x0 + 17, value)
            if fraction is not None:
                fraction = max(0.0, min(1.0, fraction))
                colour = GOOD if fraction < 0.6 else WARN if fraction < 0.85 else BAD
                y = 2 * (first + i) + 1  # lower half of the cell, so bars stay apart
                self._glow_rect(rows, x0 + 5, y, 11, 1, TRACK)
                self._glow_rect(rows, x0 + 5, y, int(round(11 * fraction)), 1, colour)


class PixelEncoder:
    """Turns pairs of pixel rows into lines of half blocks."""

    def __init__(self, mode):
        self.mode = mode
        self.night = False
        self.c16 = C16
        self.cache = {}
        self.near = {}

    def set_palette(self, c16):
        if c16 != self.c16:
            self.c16 = c16
            self.cache.clear()
            self.near.clear()

    def set_night(self, night):
        if night != self.night:
            self.night = night
            self.cache.clear()

    def _shade(self, colour):
        """The colour as shown: dimmed and bluer at night unless it glows."""
        if colour & EMISSIVE:
            return colour & RGB
        if self.night:
            return ((int((colour >> 16) * 0.36) << 16) | (int(((colour >> 8) & 255) * 0.44) << 8)
                    | int((colour & 255) * 0.68))
        return colour

    def _nearest(self, colour, limit):
        key = (colour, limit)
        if key not in self.near:
            r, g, b = colour >> 16, (colour >> 8) & 255, colour & 255
            best, best_d = 0, None
            for i in range(limit):
                p = self.c16[i]
                d = ((r - (p >> 16)) ** 2 + (g - ((p >> 8) & 255)) ** 2
                     + (b - (p & 255)) ** 2)
                if best_d is None or d < best_d:
                    best, best_d = i, d
            self.near[key] = best
        return self.near[key]

    def _fg(self, colour):
        if self.mode == "true":
            return "38;2;%d;%d;%d" % (colour >> 16, (colour >> 8) & 255, colour & 255)
        if self.mode == "256":
            return "38;5;%d" % self._cube(colour)
        n = self._nearest(colour, 16)
        return str(30 + n if n < 8 else 82 + n)

    def _bg(self, colour):
        if self.mode == "true":
            return "48;2;%d;%d;%d" % (colour >> 16, (colour >> 8) & 255, colour & 255)
        if self.mode == "256":
            return "48;5;%d" % self._cube(colour)
        return str(40 + self._nearest(colour, 8))

    @staticmethod
    def _cube(colour):
        r, g, b = colour >> 16, (colour >> 8) & 255, colour & 255
        return 16 + 36 * ((r * 5 + 127) // 255) + 6 * ((g * 5 + 127) // 255) + (b * 5 + 127) // 255

    def _codes(self, pair):
        """Returns (foreground code or None, background code, character)."""
        if len(self.cache) > 60000:
            self.cache.clear()
        top, bottom = self._shade(pair[0]), self._shade(pair[1])
        if self.mode == "16":
            a, b = self._nearest(top, 16), self._nearest(bottom, 16)
            if a == b:
                codes = (None, self._bg(top), " ") if a < 8 else (self._fg(top), self._bg(top), FULL)
            elif b < 8:
                codes = (self._fg(top), self._bg(bottom), UPPER)
            elif a < 8:
                codes = (self._fg(bottom), self._bg(top), LOWER)
            else:
                codes = (self._fg(top), self._bg(bottom), UPPER)
        elif top == bottom:
            codes = (None, self._bg(top), " ")
        else:
            codes = (self._fg(top), self._bg(bottom), UPPER)
        self.cache[pair] = codes
        return codes

    def line(self, top, bottom, text=None):
        cache = self.cache
        out = []
        cur_fg = cur_bg = None
        if text:
            cells = []
            ink = self._fg(self._shade(TEXT))
            for x, pair in enumerate(zip(top, bottom)):
                ch = text.get(x)
                if ch:
                    behind = self._shade(mix(pair[0] & RGB, pair[1] & RGB, 0.5))
                    cells.append(((ink, self._bg(behind), ch), 1))
                else:
                    cells.append((cache.get(pair) or self._codes(pair), 1))
        else:
            cells = ((cache.get(pair) or self._codes(pair), len(list(group)))
                     for pair, group in groupby(zip(top, bottom)))
        for (fg, bg, ch), n in cells:
            if fg and fg != cur_fg:
                if bg != cur_bg:
                    out.append("\x1b[%s;%sm" % (fg, bg))
                    cur_bg = bg
                else:
                    out.append("\x1b[%sm" % fg)
                cur_fg = fg
            elif bg != cur_bg:
                out.append("\x1b[%sm" % bg)
                cur_bg = bg
            out.append(ch * n)
        out.append("\x1b[0m")
        return "".join(out)


def render_pixel(tank, state, encoder, hint=False):
    w, h = tank.w, tank.h
    if w < MIN_W or h < MIN_H:
        return too_small(w, h)
    now = time.localtime()
    night = is_night(state, now)
    encoder.set_night(night)
    encoder.set_palette(tank.c16)
    rows, text = tank.draw(state, now, hint, night)
    return [encoder.line(rows[2 * y], rows[2 * y + 1], text.get(y)) for y in range(h)]


# ---------------------------------------------------------------------------
# ASCII style
# ---------------------------------------------------------------------------

# SGR colour codes. Bold plus a base colour shows as the bright colour on the
# Linux console.
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


class AsciiTank:
    style = "ascii"

    def __init__(self, n_fish, rng, scene="reef"):
        self.rng = rng
        self.scene = scene
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

    def feed(self):
        pass

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
        if state.monitor and state.metrics:
            line = "  ".join("%s %s" % (label, value) for label, value, _f in state.metrics)
            text(2, 2, line[:max(0, w - 4)], C_CLOCK)
        if hint:
            lines = hint_lines(w)
            for i, line in enumerate(lines):
                text(max(0, (w - len(line)) // 2), h - len(lines) + i, line, C_CLOCK)
        return chars, cols

    def _draw_clock(self, text, state, now):
        w, h = self.w, self.h
        label, date, suffix = clock_text(state, now)
        width = sum(len(DIGITS[ch][0]) * 2 + 2 for ch in label) - 2
        if w >= width + 4 and h >= 16:
            x = (w - width) // 2
            for ch in label:
                glyph = DIGITS[ch]
                for row, line in enumerate(glyph):
                    text(x, 2 + row, "".join(c * 2 for c in line), C_CLOCK)
                x += len(glyph[0]) * 2 + 2
            if state.date:
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
        return too_small(w, h)
    chars, cols = tank.draw(state, time.localtime(), hint)
    return [encode(chars[y], cols[y], colour) for y in range(h)]


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------

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
        elif ch == "d":
            state.date = not state.date
        elif ch == "n":
            state.night = "off" if is_night(state, time.localtime()) else "on"
        elif ch == "m":
            state.monitor = not state.monitor
        elif ch in ("[", "]"):
            size = state.clock_size or getattr(tank, "clock_u", 0)
            top = getattr(tank, "clock_max", 0)
            if size and top:
                state.clock_size = max(1, min(top, size + (1 if ch == "]" else -1)))
        elif ch == "v":
            state.style = "ascii" if state.style == "pixel" else "pixel"
        elif ch.isdigit() and 1 <= int(ch) <= len(SCENE_NAMES):
            state.scene = SCENE_NAMES[int(ch) - 1]
        elif ch == "f":
            tank.feed()
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


def colour_mode(choice):
    """Picks how pixel colours are sent: "true", "256" or "16"."""
    if choice != "auto":
        return choice
    term = os.environ.get("TERM", "")
    if term == "linux":
        return "16"
    return "true"


def console_palette(out, colours):
    """Loads a 16 colour palette into the Linux console, or resets it."""
    if colours:
        out.write("".join("\x1b]P%X%06X" % (i, c) for i, c in enumerate(colours)))
    else:
        out.write("\x1b]R")


def run(args, colour, mode):
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
    state = State(args)
    state.hint_until = time.monotonic() + 6
    encoder = PixelEncoder(mode)
    monitor = SysMon()
    own_palette = mode == "16" and os.environ.get("TERM") == "linux"
    tank = None
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
            if (tank is None or tank.style != state.style or tank.scene != state.scene
                    or new_size != size):
                if tank is None or tank.style != state.style:
                    count = tank.n_fish if tank else args.fish
                    kind = PixelTank if state.style == "pixel" else AsciiTank
                    tank = kind(count, random.Random())
                tank.scene = state.scene
                size = new_size
                tank.resize(*size)
                if own_palette:
                    console_palette(out, getattr(tank, "c16", None))
                prev = None
                out.write("\x1b[0m\x1b[2J")
            if not state.paused:
                tank.step(dt)

            if state.monitor:
                monitor.update(now)
                state.metrics = monitor.rows
            hint = now < state.hint_until
            if tank.style == "pixel":
                lines = render_pixel(tank, state, encoder, hint)
            else:
                lines = render(tank, state, colour, hint)
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
            if own_palette:
                console_palette(out, None)
            # The Linux console has no alternate screen, so clear it as well.
            out.write("\x1b[0m\x1b[2J\x1b[H\x1b[?7h\x1b[?25h\x1b[?1049l")
            out.flush()
        except OSError:
            pass
        termios.tcsetattr(fd_in, termios.TCSADRAIN, saved)
    return 0


def snapshot(args, colour, mode):
    size = shutil.get_terminal_size((80, 24))
    state = State(args)
    kind = PixelTank if state.style == "pixel" else AsciiTank
    tank = kind(args.fish, random.Random(), state.scene)
    tank.resize(size.columns, size.lines - 1)
    for _ in range(50):
        tank.step(0.1)
    if state.monitor:
        state.metrics = SysMon().sample()
    if state.style == "pixel":
        lines = render_pixel(tank, state, PixelEncoder(mode))
    else:
        lines = render(tank, state, colour)
    sys.stdout.write("\n".join(lines) + "\n")
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
        description="A fish tank that fills the terminal.",
        epilog="Keys: " + HINT,
    )
    parser.add_argument("--style", choices=("pixel", "ascii"), default="pixel",
                        help="pixel draws with coloured half blocks, ascii with "
                             "plain characters (default pixel)")
    parser.add_argument("--scene", choices=SCENE_NAMES, default="reef",
                        help="where the tank is, in the pixel style (default reef)")
    parser.add_argument("--colors", choices=("auto", "true", "256", "16"), default="auto",
                        help="colour depth for the pixel style (default auto)")
    parser.add_argument("--no-clock", action="store_true", help="start with the clock hidden")
    parser.add_argument("--no-date", action="store_true", help="start with the date hidden")
    parser.add_argument("--clock-size", type=_bounded(1, 8), metavar="N",
                        help="clock size in the pixel style, 1 to 8 (default fits the terminal)")
    parser.add_argument("--seconds", action="store_true", help="show seconds on the clock")
    parser.add_argument("--night", choices=("auto", "on", "off"), default="auto",
                        help="night lighting in the pixel style. auto follows the "
                             "clock, dark from 19:00 to 06:00 (default auto)")
    parser.add_argument("--monitor", action="store_true",
                        help="show CPU, memory, disk, temperature and load")
    parser.add_argument("--12h", dest="h12", action="store_true", help="12 hour clock")
    parser.add_argument("--fish", type=_bounded(0, MAX_FISH), metavar="N",
                        help="number of fish (default depends on the terminal size)")
    parser.add_argument("--fps", type=_bounded(1, 30), default=10, metavar="N",
                        help="frames per second, 1 to 30 (default 10)")
    parser.add_argument("--no-color", action="store_true",
                        help="draw without colour, which also selects the ascii style")
    parser.add_argument("--snapshot", action="store_true", help="print one frame and exit")
    parser.add_argument("--version", action="version", version="ascii-fish-tank " + VERSION)
    args = parser.parse_args(argv)

    colour = not args.no_color and "NO_COLOR" not in os.environ
    encoding = (sys.stdout.encoding or "").lower().replace("-", "")
    plain_term = os.environ.get("TERM", "") in ("dumb", "vt100", "vt220", "ansi")
    if not colour or encoding != "utf8" or plain_term:
        args.style = "ascii"
    mode = colour_mode(args.colors)
    if args.snapshot:
        if not sys.stdout.isatty():
            args.style, colour = "ascii", False
        return snapshot(args, colour, mode)
    return run(args, colour, mode)


if __name__ == "__main__":
    sys.exit(main())
