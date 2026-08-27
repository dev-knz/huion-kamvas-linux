"""Discover the GS1333 vendor hidraw interface through sysfs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GS1333_HID_ID = "0003:0000256C:00002008"

# Report descriptor 0 begins with a vendor-defined usage page and report ID 8.
# This differentiates it from the pen and emulated-keyboard interfaces without
# relying on a non-persistent /dev/hidraw number.
VENDOR_DESCRIPTOR_PREFIX = bytes.fromhex("06 00 ff 09 01 a1 01 85 08")


class DeviceDiscoveryError(RuntimeError):
    """Raised when the correct hidraw interface cannot be selected safely."""


@dataclass(frozen=True, slots=True)
class HidrawDevice:
    path: Path
    sysfs_path: Path


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
) -> HidrawDevice:
    """Return the unique original vendor interface for the supported tablet."""

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
        if not descriptor.startswith(VENDOR_DESCRIPTOR_PREFIX):
            continue

        matches.append(
            HidrawDevice(path=dev_root / entry.name, sysfs_path=entry.resolve())
        )

    if not matches:
        raise DeviceDiscoveryError(
            "GS1333 vendor hidraw interface not found; connect/replug the tablet "
            "and check whether HID-BPF has already replaced its descriptor"
        )
    if len(matches) > 1:
        paths = ", ".join(str(match.path) for match in matches)
        raise DeviceDiscoveryError(f"multiple GS1333 vendor interfaces found: {paths}")

    return matches[0]
