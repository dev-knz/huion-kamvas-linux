"""Read-only checks for the local GS1333/HID-BPF setup."""

from __future__ import annotations

from pathlib import Path

from .device import DeviceDiscoveryError, find_vendor_hidraw

BPF_FIRMWARE_ROOTS = (
    Path("/usr/lib/firmware/hid/bpf"),
    Path("/usr/local/lib/firmware/hid/bpf"),
)
BPF_PIN_ROOT = Path("/sys/fs/bpf/hid")


def _matching_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if "kamvas13gen3" in path.name.lower().replace("_", "").replace("-", "")
    )


def doctor() -> int:
    """Print a concise, non-mutating diagnosis and return a process status."""

    problems = 0

    try:
        device = find_vendor_hidraw()
    except DeviceDiscoveryError as error:
        print(f"hidraw vendor interface: NOT FOUND ({error})")
        problems += 1
    else:
        print(f"hidraw vendor interface: {device.path}")

    installed = [path for root in BPF_FIRMWARE_ROOTS for path in _matching_paths(root)]
    if installed:
        print("GS1333 HID-BPF object: " + ", ".join(str(path) for path in installed))
    else:
        print("GS1333 HID-BPF object: NOT FOUND in system firmware directories")
        problems += 1

    loaded = _matching_paths(BPF_PIN_ROOT)
    if loaded:
        print("GS1333 HID-BPF loaded: " + ", ".join(str(path) for path in loaded))
    else:
        print("GS1333 HID-BPF loaded: NOT FOUND under /sys/fs/bpf/hid")
        problems += 1

    return 0 if problems == 0 else 1
