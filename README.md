# kamvas-bridge

Experimental Linux support for the Huion Kamvas 13 Gen 3 (GS1333,
`256c:2008`), with an initial focus on its two physical dials.

## Current direction

The preferred input path is upstream Linux support, not a permanent userspace
driver:

```text
GS1333 hotplug -> upstream udev helpers -> HID-BPF -> evdev/libinput -> app
                                      \-> huion-switcher selects vendor mode
```

Linux now contains a device-specific HID-BPF program named
[`Huion__Kamvas13Gen3.bpf.c`](https://github.com/torvalds/linux/blob/master/drivers/hid/bpf/progs/Huion__Kamvas13Gen3.bpf.c).
It recognizes `256c:2008`, accepts the `HUION_M22c_` firmware family, fixes the
vendor descriptor, and exposes the top and bottom wheels as ordinary Linux
relative input axes. This matches the tested firmware
`HUION_M22c_250514`.

Arch's `udev-hid-bpf 2.3.0.20260703-2` package now ships both compatibility
variants of the GS1333 program. Installing the package while the tablet is
already connected does not replay the udev `add` event, however, so an installed
object is not proof that it has been attached. See [Testing](docs/testing.md)
for the exact hotplug and verification sequence.

This repository currently provides a small, dependency-free Python diagnostic
tool. It:

- finds the correct vendor `hidraw` interface without assuming `hidraw0`;
- parses only the 14-byte dial reports confirmed on real hardware;
- timestamps adjacent identical reports without dropping them;
- diagnoses the BPF objects, hwdb match, udev rules and loaded state;
- is testable without a tablet attached.

It deliberately does not add arbitrary debounce or a parallel `uinput` daemon
yet. First we will verify the upstream HID-BPF path and measure the apparent
duplicate reports. A userspace `hidraw -> uinput` bridge remains a fallback if
upstream cannot satisfy the first scroll milestone.

## Development

Python 3.11 or newer is sufficient; there are no runtime dependencies.

```bash
python -m unittest discover -s tests -v
python -m kamvas_bridge doctor
python -m kamvas_bridge capture --count 20
```

When running directly from a checkout without installing the package, set the
source directory on Python's import path:

```bash
PYTHONPATH=src python -m kamvas_bridge doctor
PYTHONPATH=src python -m kamvas_bridge capture --count 20
```

The capture command may require temporary root access until device permissions
are installed. Do not change device nodes to mode `777`.

## Documentation

- [Observed GS1333 protocol](docs/protocol.md)
- [Architecture and hotplug](docs/architecture.md)
- [Upstream and physical testing](docs/testing.md)

## Scope

Only the Huion Kamvas 13 Gen 3 / GS1333 (`256c:2008`) is supported. Buttons,
dial-center presses, profiles, GUI, service setup, and Arch packaging are not
implemented yet.

## License

No project license has been selected yet. Upstream code is linked for reference
and has not been copied into this repository.
