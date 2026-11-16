PREFIX ?= /usr/local
DESTDIR ?=

.PHONY: test lint deb install clean

test:
	python3 -m unittest discover -s tests -v

lint:
	python3 -m py_compile icloud-sync
	python3 -m pyflakes icloud-sync tests
	sh -n packaging/build-deb.sh
	desktop-file-validate data/icloud-sync.desktop

deb:
	packaging/build-deb.sh

install:
	install -Dm755 icloud-sync $(DESTDIR)$(PREFIX)/bin/icloud-sync
	install -Dm644 data/icloud-sync.desktop $(DESTDIR)$(PREFIX)/share/applications/icloud-sync.desktop
	install -Dm644 data/icloud-sync.svg $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/icloud-sync.svg
	install -Dm644 data/icloud-sync.1 $(DESTDIR)$(PREFIX)/share/man/man1/icloud-sync.1

clean:
	rm -rf dist __pycache__ tests/__pycache__
