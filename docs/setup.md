# Installer design and usage

The `setup` command automates the physically confirmed upstream and userspace
paths on CachyOS and Arch. It also installs, enables, and starts a systemd user
service for the remapper.
It also creates the default user-editable TOML mapping only when that file does
not already exist.

## Preview first

From a repository checkout:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --dry-run
```

Dry-run mode is the default and never executes a system command. It shows the
package transaction, whether `huion-switcher` must be built, the destination
files, the config file decision, the user service, the udev refresh, and the
required physical reconnect.

To preview an optional persistent Hyprland tablet-output mapping too:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --dry-run \
  --hyprland-output HDMI-A-1
```

## Apply

Run the installer as the regular desktop user:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --apply
```

For Hyprland, pass the connector that should receive pen coordinates:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --apply \
  --hyprland-output HDMI-A-1
```

`HDMI-A-1` is only the connector used during the physical test. Find the name
for the current machine with `hyprctl monitors`; setup rejects a connector that
is not active instead of saving a likely typo.

Do not prefix Python with `sudo`. The installer intentionally separates its
work by privilege:

1. it asks for an explicit confirmation;
2. on an installed system, `sudo pacman -Syu --needed` installs or updates the
   required Arch packages, including `python-evdev`;
3. the official `huion-switcher` repository is cloned and compiled as the
   current unprivileged user when it is not already installed;
4. `sudo install` copies only the switcher binary and upstream udev rule;
5. the package's GS1333 objects, rule and hwdb match are verified;
6. an active-session udev rule and persistent `uinput` module configuration are
   installed;
7. hwdb is updated, udev is reloaded, the `uinput` module is loaded, and its
   narrowly targeted udev event is replayed to apply the active-session ACL;
8. the default config is created at the XDG user-config path, or an existing
   valid config is preserved byte-for-byte;
9. a checkout-independent remapper is installed under the user's data
   directory;
10. a systemd user service is installed, enabled for login, and restarted;
11. when requested, only a clearly marked Hyprland include and project-owned
    mapping fragment are added;
12. the user is told to physically reconnect the tablet and run `doctor`.

`--yes` skips the installer's own confirmation only when used together with
`--apply`. It does not add pacman's `--noconfirm` option.

## Safety and current limits

- Only CachyOS/Arch-family systems are accepted automatically.
- No shell command strings are evaluated; commands are executed as argument
  lists.
- Source compilation does not run as root.
- Temporary source files are removed when the build finishes.
- Existing `huion-switcher` binary and rule are preserved.
- The installer does not run `huion-switcher --all`, manually attach BPF, or
  make any device node world-writable.
- Repeated runs update and restart the same user service; they do not create a
  second service or virtual pointer.
- Repeated runs never replace
  `$XDG_CONFIG_HOME/kamvas-bridge/config.toml`; an invalid existing file stops
  setup with a useful error.
- Debian, Fedora and other package managers require separately tested package
  plans before they can be enabled.

## Live ISO and kernel safety

A Live ISO is deliberately treated differently. Setup uses `pacman -Sy
--needed` for the explicit dependencies and never performs a full system
upgrade. Updating the kernel package of a running Live session can replace
`/usr/lib/modules` while the old kernel is still running, which makes
`modprobe uinput` fail until reboot.

Before making changes, setup compares `uname -r` with the available modules
directory. It stops with a recovery explanation when they do not match. On an
installed system, finish the update and reboot into the new kernel. On an
ephemeral Live system that has already entered this state, reboot the Live ISO
and rerun setup without a full upgrade.

## Automatic and manual operation

After setup and the physical reconnect, no terminal needs to remain open:

```bash
PYTHONPATH=src python -m kamvas_bridge service status
PYTHONPATH=src python -m kamvas_bridge doctor
```

Useful service controls are:

```bash
PYTHONPATH=src python -m kamvas_bridge service restart
PYTHONPATH=src python -m kamvas_bridge service disable
PYTHONPATH=src python -m kamvas_bridge service enable
journalctl --user -u kamvas-bridge.service -b
```

For foreground development, disable the service first and then run:

```bash
PYTHONPATH=src python -m kamvas_bridge service disable
PYTHONPATH=src python -m kamvas_bridge remap
```

The process lock prevents an accidental second instance even if this step is
forgotten.

Mapping edits need only validation and service restart:

```bash
PYTHONPATH=src python -m kamvas_bridge config path
PYTHONPATH=src python -m kamvas_bridge config validate
PYTHONPATH=src python -m kamvas_bridge service restart
```

## Removal

Remove the optional Hyprland block and the user service with:

```bash
PYTHONPATH=src python -m kamvas_bridge hyprland remove
PYTHONPATH=src python -m kamvas_bridge service uninstall
```

The project-owned system files may then be removed explicitly:

```bash
sudo rm /etc/udev/rules.d/70-kamvas-bridge.rules
sudo rm /etc/modules-load.d/kamvas-bridge.conf
sudo udevadm control --reload
```

This does not remove distribution packages or the separately installed
upstream `huion-switcher`. See [Hyprland](hyprland.md) for the exact persistent
mapping behavior. The remapper config is deliberately retained so a later
reinstall does not destroy the user's mappings; remove it manually only if that
is explicitly desired.
