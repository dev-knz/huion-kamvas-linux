# Architecture and hotplug

## Preferred path

```text
USB hotplug
  +-> HID add ------> hwdb + udev-hid-bpf ----> attach GS1333 program
  +-> hidraw add/bind ------> huion-switcher -> select vendor mode

 vendor reports -> attached HID-BPF -> kernel wheel and keypad events
  -> evdev/libinput
  -> Hyprland, GNOME, KDE, Sway and applications
```

This path does not need a long-running `kamvas-bridge` daemon or a systemd
service. Both upstream helpers are finite programs launched for device events:

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

## Why systemd is not used yet

A daemon must not run directly from a udev rule, but these two short helpers are
an appropriate udev use. A custom systemd unit would duplicate upstream device
matching and introduce ordering and restart behavior we do not currently need.

If clean-boot testing proves that the upstream rules are unreliable, the next
safe design would be a systemd oneshot service activated by a device unit. That
decision requires logs from a real failure after both rules were installed
before the tablet was connected.

## Userspace fallback

The fallback remains:

```text
vendor hidraw -> parser -> evidence-based deduplication -> uinput -> libinput
```

The existing parser and timestamped capture tool preserve this option. We will
only add the `uinput` output after either the upstream path fails or we need
remapping that normal compositor/application facilities cannot provide.

No time-based debounce is currently implemented. Adjacent equal packets remain
observable so that slow and fast physical captures can establish their actual
semantics.
