# Contributing

Bug reports and pull requests are welcome.

## Setup

The program is one file, `ascii_fish_tank.py`, and needs only Python 3.9 or newer. Clone the repo and run it:

```
python3 ascii_fish_tank.py
```

## Before you open a pull request

Run the tests:

```
make test
```

CI runs the same tests, then installs the program with pip, as a `.deb` and with Nix, and runs it each time.

## Rules for changes

- Standard library only. No third-party imports.
- ASCII characters and the 16 basic colours only, so the tank keeps working on the Linux console.
- No network access, no file access and no subprocesses.
- New fish go in `_FISH_RIGHT`, drawn facing right. The left-facing copy is generated.

## Releases

Change `VERSION` in `ascii_fish_tank.py` and `version` in `package.nix` to the same number, add a section to `CHANGELOG.md`, then push a tag such as `v0.2.0`. The release workflow builds the `.deb` and the Python packages and attaches them to a GitHub release.
