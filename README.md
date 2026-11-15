# ascii-fish-tank

[![CI](https://github.com/WasathTheekshana/ascii-fish-tank/actions/workflows/ci.yml/badge.svg)](https://github.com/WasathTheekshana/ascii-fish-tank/actions/workflows/ci.yml)

A fish tank for the terminal, drawn in plain ASCII. It fills the whole terminal and redraws when the window is resized. Fish swim both ways, bubbles rise, the seaweed sways and a crab walks along the sand. A large clock sits at the top and can be turned off.

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

It uses 16 colours and only ASCII characters, so it also works on the bare Linux console (the screen of the machine itself, not only over SSH). It runs on Linux, macOS and WSL.

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
| `p` or space | pause |
| `+` / `-` | add or remove a fish |
| `?` | show the key list |

## Options

```
--no-clock    start with the clock hidden
--seconds     show seconds on the clock
--12h         12 hour clock
--fish N      number of fish, 0 to 60 (default depends on the terminal size)
--fps N       frames per second, 1 to 30 (default 10)
--no-color    draw without colour (the NO_COLOR variable does the same)
--snapshot    print one frame and exit
```

The clock needs a terminal at least 16 rows tall for the large digits. In a smaller terminal it shrinks to one line in the top right corner. Below 30 by 10 the tank shows "terminal too small".

Lower `--fps` if the machine runs warm. Fewer frames means less CPU work.

## What the program touches

The program is one Python file that imports only the standard library. It opens no network connections, reads and writes no files, and starts no other programs. The only input it reads is key presses, one byte at a time, and unknown keys are ignored. Numeric options are range checked.

The Nix and `.deb` packages run Python with `-I`, so `PYTHONPATH` and the user site directory cannot replace the modules it imports. On exit, including Ctrl+C and SIGTERM, it restores the terminal settings and the cursor.

See [SECURITY.md](SECURITY.md) for how to report a problem.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The licence is [MIT](LICENSE).
