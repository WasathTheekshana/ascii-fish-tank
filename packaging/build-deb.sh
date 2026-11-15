#!/bin/sh
# Builds dist/ascii-fish-tank.deb. Needs dpkg-deb.
set -eu

cd "$(dirname "$0")/.."
version=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' ascii_fish_tank.py)

root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
pkg="$root/ascii-fish-tank"

install -Dm755 ascii_fish_tank.py "$pkg/usr/bin/ascii-fish-tank"
# Isolated mode, so PYTHONPATH cannot replace the imported modules.
sed -i '1s|.*|#!/usr/bin/python3 -I|' "$pkg/usr/bin/ascii-fish-tank"
install -Dm644 LICENSE "$pkg/usr/share/doc/ascii-fish-tank/copyright"
install -Dm644 README.md "$pkg/usr/share/doc/ascii-fish-tank/README.md"

mkdir -p "$pkg/DEBIAN"
cat > "$pkg/DEBIAN/control" <<CONTROL
Package: ascii-fish-tank
Version: $version
Section: games
Priority: optional
Architecture: all
Depends: python3 (>= 3.9)
Maintainer: Wasath Theekshana <WasathTheekshana@users.noreply.github.com>
Homepage: https://github.com/WasathTheekshana/ascii-fish-tank
Description: ASCII fish tank for the terminal
 A full screen fish tank drawn in plain ASCII, with fish, bubbles,
 seaweed and a clock that can be switched off.
CONTROL

mkdir -p dist
dpkg-deb --build --root-owner-group "$pkg" dist/ascii-fish-tank.deb
