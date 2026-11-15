PREFIX ?= /usr/local
BINDIR = $(DESTDIR)$(PREFIX)/bin

.PHONY: test install uninstall deb

test:
	python3 -m unittest discover -s tests -v

install:
	install -Dm755 ascii_fish_tank.py $(BINDIR)/ascii-fish-tank

uninstall:
	rm -f $(BINDIR)/ascii-fish-tank

deb:
	sh packaging/build-deb.sh
