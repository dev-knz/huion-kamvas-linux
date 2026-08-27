# Testing

## 1. Check the preferred upstream path

Install the loader and tools on the installed CachyOS system:

```bash
sudo pacman -S --needed udev-hid-bpf bpf
```

Check whether the packaged firmware now contains the GS1333 program:

```bash
pacman -Ql udev-hid-bpf | grep -i 'Kamvas13Gen3'
```

No output means the package does not ship the program. That is the expected
result for Arch package `2.3.0.20260703-1`; package contents can change later.
The upstream source is:

<https://github.com/torvalds/linux/blob/master/drivers/hid/bpf/progs/Huion__Kamvas13Gen3.bpf.c>

The udev-hid-bpf project documents installation of precompiled CI artifacts at:

<https://libevdev.pages.freedesktop.org/udev-hid-bpf/installing-from-ci.html>

Do not run `huion-switcher` automatically until the matching BPF is installed:
vendor mode stops the firmware-mode pen/keyboard reports, and without a
translator the kernel cannot expose the vendor reports as normal input.

After installing the matching BPF and the upstream `huion-switcher` udev rule,
unplug and reconnect the tablet. Then run:

```bash
sudo tree /sys/fs/bpf/hid
sudo libinput list-devices
sudo libinput debug-events
```

Expected first-milestone result: the top dial produces a normal vertical wheel
event and scrolls the focused browser page. The current upstream descriptor
maps the bottom dial to horizontal pan.

`bpftool prog list` alone is less convenient because it lists all BPF programs;
the pinned tree shows the program attached to each HID device.

## 2. Run hardware-independent tests

From the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

These tests cover all four confirmed dial packets, invalid values, packet
length, and selection of the vendor interface among multiple hidraw nodes.

## 3. Capture the apparent duplicates

Only use this fallback diagnostic when the tablet has been put in vendor mode
and the raw interface remains available:

```bash
sudo env PYTHONPATH=src python -m kamvas_bridge capture --count 32
```

Perform exactly this sequence, with about two seconds between groups:

1. Top dial clockwise: four deliberately slow detents.
2. Top dial counterclockwise: four deliberately slow detents.
3. Bottom dial clockwise: four deliberately slow detents.
4. Bottom dial counterclockwise: four deliberately slow detents.

If each physical detent really produces a pair, 16 detents will yield 32 parsed
reports and the command will stop automatically. Preserve the complete output,
including `elapsed_ms`, `delta_ms`, and `adjacent_identical`; those timings are
the evidence needed for a correct filter.

Do not add `sleep()` to the read loop. Sleeping can hide reports and cannot
distinguish firmware duplicates from legitimate fast rotation.
