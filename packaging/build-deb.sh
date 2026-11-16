#!/bin/sh
# Builds dist/icloud-sync_<version>_all.deb from the working tree.
# Needs only dpkg-deb; the version comes from the program itself.
set -eu
cd "$(dirname "$0")/.."

PKG=icloud-sync
ARCH=all
MAINTAINER="Antonio Rosario Intilisano <328143274+intilinux-eng@users.noreply.github.com>"
VERSION=$(python3 icloud-sync --version | awk '{print $2}')
# Reproducible timestamps: last commit date when available
EPOCH=${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct 2>/dev/null || date +%s)}

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
ROOT="$STAGE/${PKG}_${VERSION}_${ARCH}"
DOC="$ROOT/usr/share/doc/$PKG"

install -Dm755 icloud-sync               "$ROOT/usr/bin/icloud-sync"
sed -i '1s|^#!.*python3.*$|#!/usr/bin/python3|' "$ROOT/usr/bin/icloud-sync"   # Debian policy: no env in shebangs
install -Dm644 data/icloud-sync.service  "$ROOT/usr/lib/systemd/user/icloud-sync.service"
install -Dm644 data/icloud-sync.desktop  "$ROOT/usr/share/applications/icloud-sync.desktop"
install -Dm644 data/icloud-sync.svg      "$ROOT/usr/share/icons/hicolor/scalable/apps/icloud-sync.svg"
install -Dm644 data/icloud-sync.1        "$ROOT/usr/share/man/man1/icloud-sync.1"
install -Dm644 README.md                 "$DOC/README.md"
install -Dm644 packaging/copyright       "$DOC/copyright"
gzip -9n "$ROOT/usr/share/man/man1/icloud-sync.1"

# Debian-format changelog (the human one is CHANGELOG.md, shipped next to it)
cat > "$DOC/changelog" <<CHANGELOG
$PKG ($VERSION) unstable; urgency=medium

  * Release $VERSION. See CHANGELOG.md for details.

 -- $MAINTAINER  $(date -u -R -d "@$EPOCH")
CHANGELOG
chmod 644 "$DOC/changelog"
gzip -9n "$DOC/changelog"
install -Dm644 CHANGELOG.md "$DOC/NEWS.md"

mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<CONTROL
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: $MAINTAINER
Installed-Size: $(du -sk "$ROOT/usr" | cut -f1)
Section: net
Priority: optional
Depends: python3 (>= 3.11)
Recommends: python3-pyqt6, libnotify-bin, systemd
Suggests: rclone (>= 1.69)
Homepage: https://github.com/intilinux-eng/icloud-sync
Description: two-way iCloud Drive synchronization for Linux
 icloud-sync keeps a local folder in two-way sync with iCloud Drive.
 It drives rclone bisync (iclouddrive backend) and adds what is missing
 for daily use: a background service reacting to local changes through
 inotify, a lightweight check for remote changes, protection against
 mass deletion, automatic recovery, Apple login renewal reminders,
 desktop notifications and a system tray icon.
 .
 rclone 1.69 or later is required at run time; "icloud-sync setup" can
 install the official binary for the current user when the packaged one
 is missing or too old.
 .
 Independent project, not affiliated with Apple Inc.
CONTROL

chmod 644 "$ROOT/DEBIAN/control"
find "$ROOT" -exec touch -h -d "@$EPOCH" {} +
mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$ROOT" "dist/${PKG}_${VERSION}_${ARCH}.deb" >/dev/null
(cd dist && sha256sum "${PKG}_${VERSION}_${ARCH}.deb" > "${PKG}_${VERSION}_${ARCH}.deb.sha256")
echo "dist/${PKG}_${VERSION}_${ARCH}.deb"
