# Testing on CachyOS

## 1. Install the packaged HID-BPF support

On a Live image, synchronize the package databases before installing anything:

```bash
sudo pacman -Sy
sudo pacman -S --needed git python udev-hid-bpf bpf
```

On an installed, regularly updated system, use a full upgrade instead:

```bash
sudo pacman -Syu
sudo pacman -S --needed git python udev-hid-bpf bpf
```

Do not use `pacman -Sy` by itself on an installed Arch/CachyOS system because it
can leave a partial-upgrade state.

Arch/CachyOS package `udev-hid-bpf 2.3.0.20260703-2` includes both compatible
forms of the GS1333 program:

```bash
pacman -Q udev-hid-bpf
pacman -Ql udev-hid-bpf | grep -i 'Kamvas13Gen3'
```

Expected object names are `0009-Huion__Kamvas13Gen3.bpf.o` and
`0010-Huion__Kamvas13Gen3.bpf.o`. They are alternatives for different kernel
HID-BPF APIs. Leave selection to `udev-hid-bpf`; do not hardcode one variant.

Installing these files while the tablet is connected does not attach them to
the existing device. Attachment normally happens on the next physical USB
`add` event.

## 2. Install the upstream mode switcher

The HID-BPF program decodes the complete vendor-mode reports. Install the
upstream `huion-switcher` helper and its own udev rule before enabling that
mode:

```bash
sudo pacman -S --needed base-devel rust pkgconf libusb systemd-libs
git clone https://github.com/whot/huion-switcher.git
cd huion-switcher
cargo build --release --locked
sudo install -Dm755 target/release/huion-switcher \
  /usr/lib/udev/huion-switcher
sudo install -Dm644 80-huion-switcher.rules \
  /etc/udev/rules.d/80-huion-switcher.rules
cd ..
```

The rule is installed from its upstream checkout rather than copied into this
unlicensed repository. Never run `huion-switcher` alone as a persistent setup:
without the matching HID-BPF program, vendor-mode events are not usable and a
physical reconnect is required to recover firmware mode.

## 3. Activate the automatic hotplug path

With the tablet still connected, refresh the databases and rules:

```bash
sudo systemd-hwdb update
sudo udevadm control --reload
```

Then physically unplug the tablet, wait two seconds, and reconnect it. Do not
substitute `udevadm trigger` for this first test: the USB reconnect also resets
the tablet's firmware mode and gives both upstream rules a clean event sequence.

From the `kamvas-bridge` repository, verify the entire chain:

```bash
sudo env PYTHONPATH=src python -m kamvas_bridge doctor
sudo udev-hid-bpf list-devices --with-bpfs
sudo udev-hid-bpf list-loaded
```

A successful result has all of the following:

- the `udev-hid-bpf` package and both Kamvas object files are present;
- the HID-BPF udev rule and GS1333 hwdb entry are found;
- `huion-switcher` and its rule are found;
- a Kamvas object is pinned below `/sys/fs/bpf/hid`.
- `HUION Huion Tablet_GS1333 Keypad` exposes `REL_WHEEL` and `REL_HWHEEL`.

The original vendor `hidraw` interface and `HUION_FIRMWARE_ID` may no longer be
visible after HID-BPF has rebound the device. Their absence is informational
once the pinned BPF and working Keypad prove that the upstream path is active.

Physical testing confirmed the following `evtest` output from the device whose
name ends in `GS1333 Keypad`:

- top dial: `REL_WHEEL` ±1 and `REL_WHEEL_HI_RES` ±120;
- bottom dial: `REL_HWHEEL` ±1 and `REL_HWHEEL_HI_RES` ±120.

This milestone is complete. Repeating it is only necessary when validating a
new kernel, distribution package or installer change.

## 4. Diagnose an automatic-load failure

If the object is still not loaded after a physical reconnect, collect evidence
before adding another service:

```bash
sudo journalctl -b -u systemd-udevd --no-pager | \
  grep -Ei 'hid-bpf|kamvas|huion'
for gs1333_path in /sys/bus/hid/devices/0003:256C:2008.*; do
  sudo udevadm test "$gs1333_path"
done 2>&1 | grep -Ei 'hid-bpf|kamvas|huion'
```

The loop is diagnostic and tests every GS1333 HID interface. The `doctor`
output also lists every exact sysfs path and whether its hwdb property matched.

As a temporary, reversible attachment test, first confirm that the glob printed
by the next command contains only GS1333 HID paths:

```bash
printf '%s\n' /sys/bus/hid/devices/0003:256C:2008.*
```

Then load the two compatibility candidates as one group:

```bash
sudo udev-hid-bpf --verbose add \
  /sys/bus/hid/devices/0003:256C:2008.* - \
  0009-Huion__Kamvas13Gen3.bpf.o \
  0010-Huion__Kamvas13Gen3.bpf.o
sudo /usr/lib/udev/huion-switcher --all
sudo udev-hid-bpf list-loaded
```

The literal `-` separates device paths from object names. Passing both names in
one group lets the loader try its preferred API and fall back to the compatible
one. Unplugging the tablet detaches this manual test and restores a clean state.

Only if an installed system still fails on a clean boot with both upstream
rules already present should we add a systemd oneshot unit. A long-running
daemon is not needed for these finite hotplug helpers.

## 5. Run hardware-independent tests

From the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

These tests cover the four confirmed dial packets, invalid values, packet
length, discovery before and after HID-BPF descriptor fixup, and diagnostic
matching without requiring a tablet.

## 6. Preserve the hidraw fallback

The upstream path is the supported default. Use raw capture only on a system
where HID-BPF cannot be attached and the original vendor descriptor remains:

```bash
sudo env PYTHONPATH=src python -m kamvas_bridge capture --count 32
```

If fallback development becomes necessary, capture this controlled sequence
with about two seconds between groups:

1. Top dial clockwise: four deliberately slow detents.
2. Top dial counterclockwise: four deliberately slow detents.
3. Bottom dial clockwise: four deliberately slow detents.
4. Bottom dial counterclockwise: four deliberately slow detents.

If each physical detent really produces a pair, 16 detents will yield 32 parsed
reports. Preserve `elapsed_ms`, `delta_ms`, and `adjacent_identical`; those
timings are evidence needed for a correct filter. The capture command now
refuses automatic selection of an HID-BPF-fixed interface because evdev is the
correct consumer after attachment.

Do not add `sleep()` or time-based debounce to the read loop. Do not use this
parser in parallel with a working HID-BPF path.
