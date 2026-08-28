# kamvas-bridge

Linux setup, diagnostics and userspace remapping for the Huion Kamvas 13 Gen 3
(GS1333, `256c:2008`). The complete dial path has been confirmed on physical
hardware running CachyOS, Hyprland and Wayland.

## Architecture

```text
GS1333 -> huion-switcher -> HID-BPF -> evdev/libinput tablet-pad
       -> kamvas-bridge user service -> uinput virtual pointer -> applications

HID-BPF stylus -> Hyprland device mapping -> configured Kamvas output
```

Physical testing confirmed:

- the top dial scrolls vertically in real applications;
- the bottom dial emits horizontal scrolling;
- the HID-BPF stylus can be mapped exclusively to the Kamvas display;
- the uinput remapper runs without root after its targeted udev permissions are
  installed.

The normal path reads only the normalized `REL_WHEEL` and `REL_HWHEEL` events
created by upstream HID-BPF. It does not parse hidraw, duplicate the upstream
decoder, or apply arbitrary debounce. Hidraw remains a compatibility fallback
for unsupported kernels/distributions.

## Installation from a checkout

On an installed, updated CachyOS/Arch system, clone as the regular desktop user:

```bash
sudo pacman -S --needed git python
git clone https://github.com/dev-knz/huion-kamvas-linux.git
cd huion-kamvas-linux
```

Only on a fresh Live ISO whose package databases do not exist yet, bootstrap
with `sudo pacman -Sy --needed git python` instead.

Do not run the Python command itself with `sudo`. The setup requests `sudo` only
for its audited package and system-file operations.

## Setup

Preview every operation without changing the system:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --dry-run
```

Apply upstream support, permissions and the automatic remapper service:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --apply
```

For Hyprland, first list the actual outputs:

```bash
hyprctl -j monitors
```

Then pass the connector used by the Kamvas explicitly. `HDMI-A-1` is only an
example and is never assumed automatically:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --apply \
  --hyprland-output HDMI-A-1
```

The Hyprland mapping targets only the confirmed HID-BPF device
`huion-huion-tablet_gs1333-stylus`. It does not configure the older
`huion-huion-tablet_gs1333-pen` interface.

The setup is idempotent. Re-running it refreshes the managed runtime copy,
reloads the systemd user unit and restarts the remapper with the current code.
It does not overwrite the user's Hyprland configuration: it installs a separate
managed fragment and adds one marked, removable include block.

### Live ISO and kernel safety

On an installed CachyOS/Arch system, setup uses a full `pacman -Syu` transaction.
On an ArchISO/CachyOS Live environment it avoids a full upgrade and installs only
the selected packages with `pacman -Sy --needed`.

Before and after the package transaction, setup compares `uname -r` with the
available `/usr/lib/modules`/`/lib/modules` directories. If they do not match,
setup stops before `modprobe` and service activation. Reboot into the matching
installed kernel and run setup again. Do not keep updating a broken Live session
just to force the hardware test through.

## Automatic daily use

Setup installs and enables `kamvas-bridge.service` in the current user's systemd
manager. It starts at login, restarts after failures, keeps waiting when the
tablet is disconnected, and follows changing `/dev/input/event*` numbers after
hotplug. No terminal needs to remain open.

Useful controls:

```bash
PYTHONPATH=src python -m kamvas_bridge service status
PYTHONPATH=src python -m kamvas_bridge service restart
PYTHONPATH=src python -m kamvas_bridge service disable
PYTHONPATH=src python -m kamvas_bridge service enable
```

Logs:

```bash
journalctl --user -u kamvas-bridge.service -b --no-pager
```

The service executes a managed copy below
`$XDG_DATA_HOME/kamvas-bridge/runtime` (normally
`~/.local/share/kamvas-bridge/runtime`), so daily operation does not depend on
the clone remaining in the same directory.

## Manual development mode

The manual command remains available. Disable the automatic instance first so
the instance lock does not reject the second process:

```bash
PYTHONPATH=src python -m kamvas_bridge service disable
PYTHONPATH=src python -m kamvas_bridge remap
```

After testing, stop the foreground command with `Ctrl+C` and restore automatic
operation:

```bash
PYTHONPATH=src python -m kamvas_bridge service enable
```

## Hyprland output mapping

Configure or change the output without rerunning the system setup:

```bash
PYTHONPATH=src python -m kamvas_bridge hyprland configure \
  --output HDMI-A-1
PYTHONPATH=src python -m kamvas_bridge hyprland status
```

Current Hyprland Lua configurations receive `kamvas_bridge.lua` and a guarded
`pcall(require, "kamvas_bridge")` include. Legacy `hyprland.conf` configurations
receive a separate `kamvas-bridge.conf` fragment and marked `source` block.

To choose another monitor, rerun `configure` with a name from
`hyprctl -j monitors`. To remove only the project-managed mapping:

```bash
PYTHONPATH=src python -m kamvas_bridge hyprland remove
```

## Diagnosis and recovery

Run diagnostics as the regular user:

```bash
PYTHONPATH=src python -m kamvas_bridge doctor
```

Doctor distinguishes:

- missing/incomplete HID-BPF installation;
- installed but unloaded HID-BPF;
- missing GS1333 Keypad;
- evdev permission failure;
- missing or unwritable `/dev/uinput`;
- inactive, failed or active remapper service;
- missing virtual pointer;
- missing Hyprland mapping, output or HID-BPF stylus;
- Live ISO/running-kernel module mismatch.

It never runs recovery commands automatically. For an installed-but-unloaded
HID-BPF path, the documented recovery is:

```bash
sudo systemd-hwdb update
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hid
```

Then physically unplug the Kamvas, wait two seconds, reconnect it, and rerun
doctor. A fully operating configured system reports:

```text
upstream HID path: READY
remapper service: ACTIVE (running)
remapper: READY
Hyprland mapping: READY
```

## Uninstalling/reverting project changes

Remove the automatic user service and managed runtime copy:

```bash
PYTHONPATH=src python -m kamvas_bridge service uninstall
```

Remove the managed Hyprland fragment/include:

```bash
PYTHONPATH=src python -m kamvas_bridge hyprland remove
```

The two system files owned by this project can be removed explicitly:

```bash
sudo rm -f /etc/udev/rules.d/70-kamvas-bridge.rules
sudo rm -f /etc/modules-load.d/kamvas-bridge.conf
sudo udevadm control --reload
```

This intentionally does not remove `udev-hid-bpf`, `huion-switcher` or their
upstream rules because they may be useful independently. It also does not unload
`uinput`, which other applications may be using.

## Development tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The tests do not require a physical tablet, Hyprland session, systemd user bus,
or Linux input device.

## Documentation

- [Architecture and hotplug](docs/architecture.md)
- [Installer and service lifecycle](docs/setup.md)
- [Hyprland stylus mapping](docs/hyprland.md)
- [Normalized dial remapping](docs/remapping.md)
- [Testing and recovery](docs/testing.md)
- [Observed fallback protocol](docs/protocol.md)

## Scope

Only the Huion Kamvas 13 Gen 3 / GS1333 (`256c:2008`) is supported. Advanced
button actions, profiles and a GUI are not implemented yet.

## License

No project license has been selected yet. Upstream code is linked for reference
and has not been copied into this repository.
