# Architecture and hotplug

## Preferred path

```text
USB hotplug
  +-> HID add ------> hwdb + udev-hid-bpf ----> attach GS1333 program
  +-> hidraw add/bind ------> huion-switcher -> select vendor mode

 vendor reports -> attached HID-BPF -> kernel Keypad events
  -> evdev/libinput tablet-pad dials
  -> logical GS1333 controls -> configured safe actions
  -> kamvas-bridge remapper (systemd --user)
  +-> uinput virtual pointer  -> libinput pointer scroll
  +-> uinput virtual keyboard -> keyboard shortcuts/zoom
  -> Hyprland, GNOME, KDE, Sway and applications
```

The two upstream helpers are finite programs launched for device events:

- `80-huion-switcher.rules` invokes `huion-switcher` for a Huion hidraw device
  and imports `HUION_FIRMWARE_ID` and `HUION_MAGIC_BYTES` into udev;
- `81-hid-bpf.rules` looks up matching BPF objects in hwdb and invokes
  `udev-hid-bpf` for a HID `add` event.

The rules receive events from different udev subsystems, so their numeric names
do not serialize the two operations. Safety comes from installing the loader,
BPF objects, switcher, and both rules before the physical reconnect. We should
install the upstream `huion-switcher` rule unchanged instead of maintaining a
competing local copy. The helper is GPL-2.0 and remains an external dependency;
no source from it is copied into this currently unlicensed repository.

Installing a package does not recreate the `add` event for devices that are
already present. After installing or changing either rule, reload udev and
physically unplug/replug the tablet. On future boots and hotplugs, udev handles
the sequence automatically.

## Physically confirmed result

The complete path was validated on a GS1333 in CachyOS Live:

```text
GS1333 -> huion-switcher -> 0010-Huion__Kamvas13Gen3_bpf -> evdev
```

The resulting `HUION Huion Tablet_GS1333 Keypad` device exposed and emitted:

| Physical control | Normal-resolution event | High-resolution event |
| --- | --- | --- |
| Top dial | `REL_WHEEL` ±1 | `REL_WHEEL_HI_RES` ±120 |
| Bottom dial | `REL_HWHEEL` ±1 | `REL_HWHEEL_HI_RES` ±120 |

Libinput correctly converts these into `TABLET_PAD_DIAL` events for dial 0 and
dial 1. That validates the upstream decoder, but tablet-pad dials are not
pointer axes and therefore do not scroll Firefox automatically.

The main userspace component maps already normalized low-resolution dial and
`BTN_0`–`BTN_6` events through the user's TOML configuration. It ignores the
high-resolution dial companions to avoid duplicate output. Scroll actions use
the existing virtual pointer; shortcuts and bottom-dial zoom use a separate
virtual keyboard with a finite capability set. There is still no reason to
decode GS1333 vendor packets again in the normal userspace path.

The complete path through the virtual pointer was then physically confirmed:
the top dial scrolls vertically and the bottom dial scrolls horizontally in
applications. That confirms the original pointer path; the new configurable
button shortcuts and bottom-dial keyboard zoom still need final hardware
validation.

## Process model

The remapper is a long-running user-session process. It scans for the Keypad by
device name plus USB vendor/product IDs, watches reconnects, and never matches
its differently named virtual pointer. Setup installs a systemd user service,
enables it for the user's `default.target`, and starts it immediately. The unit
runs without root and restarts on unexpected failure. Its executable Python
package is copied into the user's data directory, so the service does not
depend on keeping the cloned repository in the same place.

The process also takes a per-user runtime lock. A second service or foreground
copy exits instead of creating duplicate virtual devices. For development, the
service can be disabled before running `kamvas-bridge remap` manually.

Configuration is loaded once at process start from the XDG config directory.
The setup command creates defaults only when the file is absent, and service
restart applies later edits. The action parser accepts only named internal
actions and bounded keyboard chords; it has no shell or command execution path.

The udev permission rule grants the active local session access to the specific
GS1333 event device, `/dev/uinput`, and the identified virtual pointer event
and virtual keyboard event nodes that `python-evdev` opens during construction.
Access to uinput permits input injection, so it is deliberately scoped with
`TAG+="uaccess"` instead of a world-writable device mode.

## Project priorities

Development should proceed in this order:

1. diagnose the complete upstream path;
2. guide or automate safe `huion-switcher` installation and configuration
   (`setup --dry-run` and `setup --apply` now cover CachyOS/Arch);
3. verify `udev-hid-bpf`, its objects, hwdb and rules;
4. detect kernel/distribution support and present actionable recovery steps;
5. verify the automatic user service and persistent compositor mapping;
6. physically validate configurable buttons and bottom-dial zoom;
7. consider profiles and a GUI only after the action model is stable.

## Userspace fallback

For a kernel or distribution without usable HID-BPF support, the fallback
remains:

```text
vendor hidraw -> parser -> evidence-based deduplication -> uinput -> libinput
```

The existing parser and timestamped capture tool preserve this option. A
hidraw-backed output path should only be implemented for a demonstrated
compatibility gap; the normal uinput remapper is not a reason to duplicate
upstream packet parsing.

No time-based debounce is currently implemented. Adjacent equal packets remain
observable in fallback captures if a future unsupported system requires that
investigation.
