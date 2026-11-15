# Changelog

## 0.3.0

- Four scenes, picked with the keys `1` to `4` or `--scene`: reef, lagoon, kelp forest and deep sea.
- New fish: butterflyfish, sardines, anglerfish and lanternfish. A sea turtle swims in the lagoon.
- Jellyfish glow in the deep sea and swim in pulses.
- Coral grows on the reef and in the lagoon.
- The clock is drawn over the far plants, so tall kelp does not hide it.
- The Linux console gets a 16 colour palette for each scene.

## 0.2.0

- New pixel style, now the default. It draws two coloured pixels per character with half blocks, in 24-bit, 256 or 16 colours.
- Fish are drawn from shape and colour descriptions: clownfish, blue tang, angelfish, goldfish, neon tetra schools and a shark.
- Fish come in three depths. Far ones are smaller and fade into the water.
- Water gets darker with depth and has moving light rays and surface waves.
- Plants sway along their whole length. Sand has dunes, grain and rocks.
- `f` drops food and nearby fish swim to it.
- `v` switches between the pixel and ASCII styles.
- The clock in the pixel style is a seven segment display that the fish swim in front of.
- The date is drawn in pixel letters that glow like the clock. `d` hides it.
- `[` and `]` change the clock size.
- Shells, starfish and urchins lie on the sand, and crabs and snails walk across it.
- Night lighting, automatic from 19:00 to 06:00 or switched with `n`, with glowing plankton.
- System monitor panel with CPU, memory, disk, temperature and load, switched with `m`.
- The key list wraps to fit narrow terminals.
- New options `--style`, `--colors`, `--no-date`, `--clock-size`, `--night` and `--monitor`.

## 0.1.0

First release.

- Fish in six shapes, bubbles, seaweed, a crab and a castle.
- Large clock with date. It can be hidden, show seconds, and use 12 or 24 hour time.
- Packages for Nix, pip and Debian/Ubuntu.
