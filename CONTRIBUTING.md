# Contributing

Bug reports and pull requests are welcome.

## Setup

The program is one file, `ascii_fish_tank.py`, and needs only Python 3.10 or newer. Clone the repo and run it:

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
- The ASCII style uses ASCII characters and the 16 basic colours only, so it works on any terminal.
- The pixel style uses only the half block, full block and space characters.
- No network access, no file writes and no subprocesses. Only the system monitor reads files.
- A new pixel fish is an entry in `SPECIES` plus a colour function. A new ASCII fish goes in `_FISH_RIGHT`. Both are drawn facing right and the left-facing copy is generated.

## Releases

Change `VERSION` in `ascii_fish_tank.py` and `version` in `package.nix` to the same number, add a section to `CHANGELOG.md`, then push a tag such as `v0.2.0`. The release workflow builds the `.deb` and the Python packages and attaches them to a GitHub release.
