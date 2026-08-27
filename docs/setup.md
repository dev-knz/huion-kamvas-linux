# Installer design and usage

The `setup` command automates the confirmed upstream path on CachyOS and Arch.
It prepares the foreground userspace remapper but does not install a persistent
daemon or user service yet.

## Preview first

From a repository checkout:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --dry-run
```

Dry-run mode is the default and never executes a system command. It shows the
package transaction, whether `huion-switcher` must be built, the destination
files, the udev refresh, and the required physical reconnect.

## Apply

Run the installer as the regular desktop user:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --apply
```

Do not prefix Python with `sudo`. The installer intentionally separates its
work by privilege:

1. it asks for an explicit confirmation;
2. `sudo pacman -Syu --needed` installs or updates the required Arch packages,
   including `python-evdev`;
3. the official `huion-switcher` repository is cloned and compiled as the
   current unprivileged user when it is not already installed;
4. `sudo install` copies only the switcher binary and upstream udev rule;
5. the package's GS1333 objects, rule and hwdb match are verified;
6. an active-session udev rule and persistent `uinput` module configuration are
   installed;
7. hwdb is updated, udev is reloaded, the `uinput` module is loaded, and its
   narrowly targeted udev event is replayed to apply the active-session ACL;
8. the user is told to physically reconnect the tablet and start `remap`.

`--yes` skips the installer's own confirmation only when used together with
`--apply`. It does not add pacman's `--noconfirm` option.

## Safety and current limits

- Only CachyOS/Arch-family systems are accepted automatically.
- No shell command strings are evaluated; commands are executed as argument
  lists.
- Source compilation does not run as root.
- Temporary source files are removed when the build finishes.
- Existing `huion-switcher` binary and rule are preserved.
- The installer does not run `huion-switcher --all`, manually attach BPF, start
  a service, or make any device node world-writable.
- Debian, Fedora and other package managers require separately tested package
  plans before they can be enabled.

After the physical reconnect, start the foreground remapper without sudo:

```bash
PYTHONPATH=src python -m kamvas_bridge remap
```

Then run `PYTHONPATH=src python -m kamvas_bridge doctor` in another terminal.
Success reports `upstream HID path: READY` and `remapper: READY`.
