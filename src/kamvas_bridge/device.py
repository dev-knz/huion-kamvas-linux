"""Discover the GS1333 vendor hidraw interface through sysfs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

GS1333_HID_ID = "0003:0000256C:00002008"

# Report descriptor 0 begins with a vendor-defined usage page and report ID 8.
# This differentiates it from the pen and emulated-keyboard interfaces without
# relying on a non-persistent /dev/hidraw number.
VENDOR_DESCRIPTOR_PREFIX = bytes.fromhex("06 00 ff 09 01 a1 01 85 08")
BPF_FIXED_VENDOR_DESCRIPTOR_PREFIX = bytes.fromhex("05 0d 09 02 a1 01 85 08")


class DeviceDiscoveryError(RuntimeError):
    """Raised when the correct hidraw interface cannot be selected safely."""


class DescriptorState(Enum):
    ORIGINAL = "original descriptor"
    HID_BPF_FIXED = "HID-BPF fixed descriptor"


@dataclass(frozen=True, slots=True)
class HidrawDevice:
    path: Path
    sysfs_path: Path
    descriptor_state: DescriptorState


def _read_uevent(path: Path) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value
    return properties


def find_vendor_hidraw(
    sys_class_hidraw: Path = Path("/sys/class/hidraw"),
    dev_root: Path = Path("/dev"),
    *,
    require_original: bool = False,
) -> HidrawDevice:
    """Return the unique vendor interface for the supported tablet.

    After HID-BPF attaches, the vendor-defined descriptor is replaced with a
    digitizer/keypad descriptor. Both forms are recognized for diagnostics,
    while raw capture can require the original descriptor explicitly.
    """

    matches: list[HidrawDevice] = []

    if not sys_class_hidraw.is_dir():
        raise DeviceDiscoveryError(f"hidraw sysfs class not found: {sys_class_hidraw}")

    for entry in sorted(sys_class_hidraw.glob("hidraw*")):
        device_dir = entry / "device"
        try:
            properties = _read_uevent(device_dir / "uevent")
            descriptor = (device_dir / "report_descriptor").read_bytes()
        except (FileNotFoundError, PermissionError, OSError):
            continue

        if properties.get("HID_ID", "").upper() != GS1333_HID_ID:
            continue

        if descriptor.startswith(VENDOR_DESCRIPTOR_PREFIX):
            descriptor_state = DescriptorState.ORIGINAL
        elif descriptor.startswith(BPF_FIXED_VENDOR_DESCRIPTOR_PREFIX):
            descriptor_state = DescriptorState.HID_BPF_FIXED
        else:
            continue
        if require_original and descriptor_state is not DescriptorState.ORIGINAL:
            continue

        matches.append(
            HidrawDevice(
                path=dev_root / entry.name,
                sysfs_path=entry.resolve(),
                descriptor_state=descriptor_state,
            )
        )

    if not matches:
        raise DeviceDiscoveryError(
            "GS1333 vendor hidraw interface not found; connect/replug the tablet "
            "and inspect the HID-BPF state"
        )
    if len(matches) > 1:
        paths = ", ".join(str(match.path) for match in matches)
        raise DeviceDiscoveryError(f"multiple GS1333 vendor interfaces found: {paths}")

    return matches[0]
