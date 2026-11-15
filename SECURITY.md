# Security

## Reporting a problem

Please report security problems privately, through the "Report a vulnerability" button on the repository's Security tab. Do not open a public issue for them.

Only the latest release gets fixes.

## What the program can do

The program draws to the terminal and reads key presses. It opens no network connections, reads and writes no files, and starts no other programs. It has no dependencies outside the Python standard library.

The Nix and `.deb` packages run Python with `-I` (isolated mode), so `PYTHONPATH` and the user site directory cannot replace the modules it imports.
