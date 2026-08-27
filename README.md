# kamvas-bridge

Linux setup, diagnostics and dial remapping for the Huion Kamvas 13 Gen 3
(GS1333, `256c:2008`). The upstream HID path has been confirmed on physical
hardware.

## Current direction

The primary input path keeps upstream Linux responsible for decoding the
tablet, then translates normalized tablet-pad dials into pointer scrolling:

```text
GS1333 -> huion-switcher -> HID-BPF -> evdev/libinput tablet-pad
       -> kamvas-bridge remapper -> uinput virtual pointer/keyboard -> applications
```

Linux now contains a device-specific HID-BPF program named
[`Huion__Kamvas13Gen3.bpf.c`](https://github.com/torvalds/linux/blob/master/drivers/hid/bpf/progs/Huion__Kamvas13Gen3.bpf.c).
It recognizes `256c:2008`, accepts the `HUION_M22c_` firmware family, fixes the
vendor descriptor, and exposes the top and bottom wheels as ordinary Linux
relative input axes. This matches the tested firmware
`HUION_M22c_250514`.

Physical testing on CachyOS Live confirmed that the kernel selects
`0010-Huion__Kamvas13Gen3_bpf` and creates
`HUION Huion Tablet_GS1333 Keypad` with:

- top dial: `REL_WHEEL` ±1 and `REL_WHEEL_HI_RES` ±120;
- bottom dial: `REL_HWHEEL` ±1 and `REL_HWHEEL_HI_RES` ±120.

Libinput exposes those events as `TABLET_PAD_DIAL`, which browsers do not treat
as pointer scroll automatically. The HID-BPF program already parses the vendor
reports correctly, so the remapper reads only normalized evdev events and emits
scroll events through a virtual pointer. A virtual keyboard output is reserved
for future configurable actions; the initial dial milestone does not need it.
The remapper does not parse hidraw.

Arch's `udev-hid-bpf 2.3.0.20260703-2` package now ships both compatibility
variants of the GS1333 program. Installing the package while the tablet is
already connected does not replay the udev `add` event, however, so an installed
object is not proof that it has been attached. See [Testing](docs/testing.md)
for the exact hotplug and verification sequence.

This repository provides a Python setup, diagnostic and remapping tool. It:

- checks the installed `udev-hid-bpf` package and GS1333 object files;
- diagnoses hwdb matching, udev rules and the loaded BPF state;
- verifies `huion-switcher` and its udev rule;
- verifies that the GS1333 Keypad exposes vertical and horizontal wheel axes;
- maps dial 0 to vertical pointer scroll and dial 1 to horizontal scroll;
- handles changing `/dev/input/event*` numbers and reconnects dynamically;
- creates a clearly named virtual pointer and never reads it as an input source;
- retains raw-report capture for fallback investigation;
- is testable without a tablet attached.

The next milestone is physical confirmation that dial 0 scrolls Firefox through
the virtual pointer. After that come configurable dial/button actions, profiles,
automatic user-session startup and a GUI. A userspace
`hidraw -> uinput` bridge remains a compatibility fallback for distributions or
kernels that cannot run the upstream path. It is no longer the primary design,
and no arbitrary debounce is implemented.

## Development

Python 3.11 or newer and `python-evdev` are required on Linux.

```bash
python -m unittest discover -s tests -v
python -m kamvas_bridge doctor
python -m kamvas_bridge remap
python -m kamvas_bridge capture --count 20
```

When running directly from a checkout without installing the package, set the
source directory on Python's import path:

```bash
PYTHONPATH=src python -m kamvas_bridge doctor
PYTHONPATH=src python -m kamvas_bridge remap
PYTHONPATH=src python -m kamvas_bridge capture --count 20
```

## CachyOS/Arch setup

Preview the complete installation without changing the system:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --dry-run
```

Apply it as your normal user, without putting `sudo` before Python:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --apply
```

The installer asks for confirmation, uses `sudo` only for package and system
file operations, builds `huion-switcher` without root privileges, validates the
packaged GS1333 objects, and reloads hwdb/udev. It never switches the connected
tablet directly; the final activation remains a physical unplug/replug.

After reconnecting the tablet, run the remapper as the normal desktop user:

```bash
PYTHONPATH=src python -m kamvas_bridge remap
```

Keep it running while testing Firefox. In another terminal, `doctor` reports
the upstream HID path and remapper readiness separately.

The capture command may require temporary root access until device permissions
are installed. It is for fallback investigation only. Do not change device
nodes to mode `777`.

## Documentation

- [Observed GS1333 protocol](docs/protocol.md)
- [Architecture and hotplug](docs/architecture.md)
- [Installer design and usage](docs/setup.md)
- [Normalized dial remapping](docs/remapping.md)
- [Upstream and physical testing](docs/testing.md)

## Scope

Only the Huion Kamvas 13 Gen 3 / GS1333 (`256c:2008`) is supported. Buttons,
dial-center presses, profiles, remapping UI, GUI, installers for distributions
outside CachyOS/Arch, and distribution packaging are not implemented yet.

## License

No project license has been selected yet. Upstream code is linked for reference
and has not been copied into this repository.
