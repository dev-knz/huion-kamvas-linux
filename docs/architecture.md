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

This establishes the upstream path as the project architecture for the dials.
There is no reason to decode the same GS1333 vendor packets again in a normal
userspace daemon.

## Why systemd is not used yet

A daemon must not run directly from a udev rule, but these two short helpers are
an appropriate udev use. A custom systemd unit would duplicate upstream device
matching and introduce ordering and restart behavior we do not currently need.

The upstream udev path succeeded after installing both components and physically
reconnecting the tablet. A custom unit should only be reconsidered if a specific
distribution demonstrates a reproducible ordering or hotplug failure.

## Project priorities

Development should proceed in this order:

1. diagnose the complete upstream path;
2. guide or automate safe `huion-switcher` installation and configuration;
3. verify `udev-hid-bpf`, its objects, hwdb and rules;
4. detect kernel/distribution support and present actionable recovery steps;
5. add remapping and profiles using normal evdev/compositor facilities;
6. provide a GUI after the configuration model is stable.

## Userspace fallback

For a kernel or distribution without usable HID-BPF support, the fallback
remains:

```text
vendor hidraw -> parser -> evidence-based deduplication -> uinput -> libinput
```

The existing parser and timestamped capture tool preserve this option. A
`uinput` output layer should only be implemented for a demonstrated
compatibility gap; remapping alone is not a reason to duplicate upstream packet
parsing.

No time-based debounce is currently implemented. Adjacent equal packets remain
observable in fallback captures if a future unsupported system requires that
investigation.
