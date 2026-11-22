# Dolphin emblems for icloud-sync

A small plugin that shows the sync state of every file in Dolphin and in KDE file dialogs:

| Emblem | Meaning |
|---|---|
| green check (`vcs-normal`) | identical to what the last sync recorded |
| arrows (`vcs-update-required`) | new or edited since then: it will go up at the next sync |
| red mark (`vcs-conflicting`) | a conflict copy kept by the sync (`name.conflict1.ext`) |
| "unavailable" mark (`emblem-unavailable`) | an item iCloud does not let rclone download (shared folders, iWork documents): it stays on iCloud only, see `icloud-sync skipped` |

Hidden files and the names excluded in `config.toml` get no emblem, because they are never synced.

## How it works

After every successful sync the icloud-sync daemon writes
`~/.local/state/icloud-sync/overlay-state.tsv`: path, size and modification time (in milliseconds) of
everything it has just synced. The plugin compares each file on disk with that record. It never talks
to iCloud and never touches your files.

## Build and install

It needs CMake, a C++ compiler, extra-cmake-modules and the KIO development files
(`sudo apt install cmake g++ extra-cmake-modules libkf6kio-dev` on Debian and Ubuntu).

```bash
cmake -S dolphin -B dolphin/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr
cmake --build dolphin/build
ctest --test-dir dolphin/build
sudo cmake --install dolphin/build
```

Then restart Dolphin. To remove it, delete `icloudsyncoverlay.so` from the `kf6/overlayicon` folder of
your Qt plugins (the install step prints the path).

## Limits

- A folder shows the check mark as soon as the folder itself is known, even while a file inside it is
  still waiting.
- The emblem of a file you have just edited changes when Dolphin refreshes that item.
- The plugin is not part of the `.deb` yet: it is compiled code, so it needs a package per architecture.
