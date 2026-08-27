"""Read-only checks for the local GS1333/HID-BPF setup."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .device import DeviceDiscoveryError, find_vendor_hidraw

BPF_FIRMWARE_ROOTS = (
    Path("/usr/lib/firmware/hid/bpf"),
    Path("/usr/local/lib/firmware/hid/bpf"),
)
BPF_PIN_ROOT = Path("/sys/fs/bpf/hid")
HID_DEVICES_ROOT = Path("/sys/bus/hid/devices")

HID_BPF_RULE_PATHS = (
    Path("/etc/udev/rules.d/81-hid-bpf.rules"),
    Path("/usr/lib/udev/rules.d/81-hid-bpf.rules"),
    Path("/lib/udev/rules.d/81-hid-bpf.rules"),
)
HID_BPF_HWDB_ROOTS = (
    Path("/etc/udev/hwdb.d"),
    Path("/usr/lib/udev/hwdb.d"),
    Path("/lib/udev/hwdb.d"),
)

HUION_SWITCHER_PATHS = (
    Path("/usr/lib/udev/huion-switcher"),
    Path("/usr/local/lib/udev/huion-switcher"),
    Path("/usr/bin/huion-switcher"),
)
HUION_SWITCHER_RULE_PATHS = (
    Path("/etc/udev/rules.d/80-huion-switcher.rules"),
    Path("/usr/lib/udev/rules.d/80-huion-switcher.rules"),
    Path("/lib/udev/rules.d/80-huion-switcher.rules"),
)


def _normalized_name(path: Path) -> str:
    return path.name.lower().replace("_", "").replace("-", "")


def _matching_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path for path in root.rglob("*") if "kamvas13gen3" in _normalized_name(path)
    )


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def _matching_hwdb_files(roots: tuple[Path, ...] = HID_BPF_HWDB_ROOTS) -> list[Path]:
    matches: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*hid-bpf*.hwdb")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            normalized = text.lower()
            if "p00002008" in normalized and "kamvas13gen3.bpf.o" in normalized:
                matches.append(path)
    return matches


def _gs1333_hid_devices(root: Path = HID_DEVICES_ROOT) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.name.upper().startswith("0003:256C:2008.")
    )


def _parse_properties(output: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value
    return properties


def _udev_properties(*, path: Path | None = None, name: Path | None = None) -> dict[str, str]:
    udevadm = shutil.which("udevadm")
    if udevadm is None:
        return {}

    command = [udevadm, "info", "--query=property"]
    if path is not None:
        command.extend(("--path", str(path)))
    elif name is not None:
        command.extend(("--name", str(name)))
    else:
        raise ValueError("path or name is required")

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    return _parse_properties(result.stdout)


def _bpf_match_properties(properties: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in properties.items()
        if key.startswith("HID_BPF_") and "Kamvas13Gen3.bpf.o" in value
    }


def doctor() -> int:
    """Print a concise, non-mutating diagnosis and return a process status."""

    problems = 0
    vendor_device = None

    try:
        vendor_device = find_vendor_hidraw()
    except DeviceDiscoveryError as error:
        print(f"hidraw vendor interface: NOT FOUND ({error})")
        problems += 1
    else:
        print(
            f"hidraw vendor interface: {vendor_device.path} "
            f"({vendor_device.descriptor_state.value})"
        )

    installed = [path for root in BPF_FIRMWARE_ROOTS for path in _matching_paths(root)]
    if installed:
        print("GS1333 HID-BPF objects: " + ", ".join(str(path) for path in installed))
    else:
        print("GS1333 HID-BPF objects: NOT FOUND in system firmware directories")
        problems += 1

    loader_rule = _first_existing(HID_BPF_RULE_PATHS)
    print(f"udev-hid-bpf rule: {loader_rule or 'NOT FOUND'}")
    if loader_rule is None:
        problems += 1

    hwdb_files = _matching_hwdb_files()
    if hwdb_files:
        print("GS1333 HID-BPF hwdb match: " + ", ".join(str(path) for path in hwdb_files))
    else:
        print("GS1333 HID-BPF hwdb match: NOT FOUND")
        problems += 1

    hid_devices = _gs1333_hid_devices()
    matched_devices = 0
    if hid_devices:
        print(f"GS1333 HID devices: {len(hid_devices)}")
        for device in hid_devices:
            matches = _bpf_match_properties(_udev_properties(path=device))
            if matches:
                matched_devices += 1
                values = ", ".join(
                    f"{key}={value}" for key, value in sorted(matches.items())
                )
                print(f"  {device.name}: {values}")
            else:
                print(f"  {device.name}: no Kamvas13Gen3 HID_BPF property")
    else:
        print("GS1333 HID devices: NOT FOUND")
        problems += 1

    switcher = _first_existing(HUION_SWITCHER_PATHS)
    switcher_rule = _first_existing(HUION_SWITCHER_RULE_PATHS)
    print(f"huion-switcher binary: {switcher or 'NOT FOUND'}")
    print(f"huion-switcher udev rule: {switcher_rule or 'NOT FOUND'}")
    if switcher is None or switcher_rule is None:
        problems += 1

    firmware_id = None
    if vendor_device is not None:
        firmware_id = _udev_properties(name=vendor_device.path).get("HUION_FIRMWARE_ID")
    print(f"HUION_FIRMWARE_ID property: {firmware_id or 'NOT FOUND'}")
    if firmware_id is None:
        problems += 1

    loaded = _matching_paths(BPF_PIN_ROOT)
    if loaded:
        print("GS1333 HID-BPF loaded: " + ", ".join(str(path) for path in loaded))
    else:
        print("GS1333 HID-BPF loaded: NOT FOUND under /sys/fs/bpf/hid")
        problems += 1

    if installed and loader_rule and hwdb_files and hid_devices and not loaded:
        if matched_devices == 0:
            print("next: reload the hwdb/udev rules, then unplug and reconnect the tablet")
        else:
            print(
                "next: unplug and reconnect the tablet; package installation "
                "does not replay add events"
            )
    if switcher is None or switcher_rule is None:
        print("next: install upstream huion-switcher and its 80-huion-switcher.rules file")

    return 0 if problems == 0 else 1
