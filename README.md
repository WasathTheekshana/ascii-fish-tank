# ascii-fish-tank

[![CI](https://github.com/WasathTheekshana/ascii-fish-tank/actions/workflows/ci.yml/badge.svg)](https://github.com/WasathTheekshana/ascii-fish-tank/actions/workflows/ci.yml)

A fish tank that fills the terminal. Clownfish, blue tangs, angelfish, goldfish and schools of neon tetras swim between swaying plants, and now and then a shark passes through. Light falls in rays from the surface, bubbles rise from the sand, and you can drop food for the fish to chase. A large clock sits in the water and can be turned off.

![The tank at 120 by 34 characters](docs/screenshot.png)

The picture above is the pixel style at 120 by 34 characters. Each character cell holds two pixels, one above the other, so the tank has twice the vertical detail of normal terminal text. The fish are not stored pictures. They are drawn from a shape and colour description at whatever size the tank needs.

There is also a plain ASCII style, for terminals without colour or Unicode:

```
^^^~~~-----~~~~~~~~~--------~~~~~~~~~----~~~^^^^^^~~~-----~~~~~~~~~--------~~~

            ######  ######      ######  ######
                ##  ##  ##  ##      ##  ##  ##                   ><{{{*>
            ######  ##  ##      ######  ######    ,--.
            ##      ##  ##  ##      ##      ##  <o    >=<
            ######  ######      ######  ######    `--'

       /\                   Sun 15 Nov 2026            O
     _/  \                                                           <><
    <o    )><                                          o
      \_  /        (                                              _   _   _
        \/         (        )                (         .         | |_| |_| |
   (                )       )        (       (                   |         |
   (                )      (          )       )                  |   ,-.   |
    )              (       (          )       )                  |   | |   |
    )   o@   V(o,o)V       (         (       (                   |___|_|___|
:..,._;_:.,;._:,,.:,.._,.,..,.;,.,;_:_;._;..:___,:.;:;.__,::,:;_.;.;_,.:,:,_,.
```

Press `v` to switch between the two while it runs. It runs on Linux, macOS and WSL.

## Install

### Nix

Run it without installing:

```
nix run github:WasathTheekshana/ascii-fish-tank
```

Install it into your profile:

```
nix profile install github:WasathTheekshana/ascii-fish-tank
```

If flakes are not enabled, add `--extra-experimental-features "nix-command flakes"` to either command.

On NixOS with a flake config, add the repo as an input and put the package in `environment.systemPackages`:

```nix
inputs.ascii-fish-tank.url = "github:WasathTheekshana/ascii-fish-tank";

environment.systemPackages = [
  inputs.ascii-fish-tank.packages.${pkgs.system}.default
];
```

### Ubuntu and Debian

Download the `.deb` from the latest release and install it with apt:

```
curl -LO https://github.com/WasathTheekshana/ascii-fish-tank/releases/latest/download/ascii-fish-tank.deb
sudo apt install ./ascii-fish-tank.deb
```

Remove it with `sudo apt remove ascii-fish-tank`.

### pipx or pip

This works on any system with Python 3.10 or newer:

```
pipx install git+https://github.com/WasathTheekshana/ascii-fish-tank
```

### From source

```
git clone https://github.com/WasathTheekshana/ascii-fish-tank
cd ascii-fish-tank
sudo make install
```

`make install` copies one file to `/usr/local/bin`. Set `PREFIX` to install somewhere else. You can also skip the install and run `python3 ascii_fish_tank.py`.

## Keys

| Key | Action |
|---|---|
| `q` or `Esc` | quit |
| `c` | show or hide the clock |
| `s` | show or hide seconds |
| `t` | switch between 12 and 24 hour time |
| `f` | drop food (pixel style) |
| `v` | switch between the pixel and ASCII styles |
| `p` or space | pause |
| `+` / `-` | add or remove a fish |
| `?` | show the key list |

## Options

```
--style pixel|ascii        how the tank is drawn (default pixel)
--colors auto|true|256|16  colour depth for the pixel style (default auto)
--no-clock                 start with the clock hidden
--seconds                  show seconds on the clock
--12h                      12 hour clock
--fish N                   number of fish, 0 to 60 (default depends on the terminal size)
--fps N                    frames per second, 1 to 30 (default 10)
--no-color                 no colour, which also selects the ASCII style
--snapshot                 print one frame and exit
```

A smaller font gives a more detailed tank, because the tank has one pixel per half character. Zoom the terminal out (usually Ctrl and minus) to see more.

Below 30 by 10 characters the tank shows "terminal too small". Lower `--fps` if the machine runs warm.

## Colours

The pixel style sends 24-bit colour by default. Most current terminals support it, including Windows Terminal, GNOME Terminal, Konsole, kitty, Alacritty and iTerm2. If the colours come out wrong, try `--colors 256`.

On the Linux console (the screen of the machine itself, `TERM=linux`) only 16 colours exist. There the program loads its own 16 colour palette while it runs and puts the default palette back on exit. The picture is coarser than in a 24-bit terminal. If the console font has no block characters, use `--style ascii`.

## What the program touches

The program is one Python file that imports only the standard library. It opens no network connections, reads and writes no files, and starts no other programs. The only input it reads is key presses, one byte at a time, and unknown keys are ignored. Numeric options are range checked.

The Nix and `.deb` packages run Python with `-I`, so `PYTHONPATH` and the user site directory cannot replace the modules it imports. On exit, including Ctrl+C and SIGTERM, it restores the terminal settings and the cursor.

See [SECURITY.md](SECURITY.md) for how to report a problem.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The licence is [MIT](LICENSE).
