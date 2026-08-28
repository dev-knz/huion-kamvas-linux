"""Read-only checks for the local GS1333/HID-BPF setup."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from .device import DeviceDiscoveryError, find_vendor_hidraw
from .environment import runtime_environment
from .hyprland import STYLUS_DEVICE_NAME, hyprland_status
from .service import SERVICE_NAME, user_service_state

BPF_FIRMWARE_ROOTS = (
    Path("/usr/lib/firmware/hid/bpf"),
    Path("/usr/local/lib/firmware/hid/bpf"),
)
BPF_PIN_ROOT = Path("/sys/fs/bpf/hid")
HID_DEVICES_ROOT = Path("/sys/bus/hid/devices")
INPUT_CLASS_ROOT = Path("/sys/class/input")
INPUT_DEVICE_ROOT = Path("/dev/input")

KEYPAD_NAME = "HUION Huion Tablet_GS1333 Keypad"
KEYPAD_VENDOR_ID = 0x256C
KEYPAD_PRODUCT_ID = 0x2008
VIRTUAL_POINTER_NAME = "kamvas-bridge Virtual Pointer"
VIRTUAL_VENDOR_ID = 0x1209
VIRTUAL_PRODUCT_ID = 0x4B42
REL_CAPABILITY_NAMES = {
    8: "REL_WHEEL",
    11: "REL_WHEEL_HI_RES",
    6: "REL_HWHEEL",
    12: "REL_HWHEEL_HI_RES",
}
REQUIRED_KEYPAD_REL_CODES = frozenset((6, 8))

REMAPPER_RULE_PATHS = (
    Path("/etc/udev/rules.d/70-kamvas-bridge.rules"),
    Path("/usr/lib/udev/rules.d/70-kamvas-bridge.rules"),
)
MODULES_LOAD_PATHS = (
    Path("/etc/modules-load.d/kamvas-bridge.conf"),
    Path("/usr/lib/modules-load.d/kamvas-bridge.conf"),
)
UINPUT_PATH = Path("/dev/uinput")

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


@dataclass(frozen=True, slots=True)
class KeypadDevice:
    path: Path
    sysfs_path: Path
    relative_codes: frozenset[int]
    vendor_id: int
    product_id: int


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


def _run_command(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = result.stdout.strip()
    return output or None


def _udev_hid_bpf_package() -> str | None:
    queries = (
        ("pacman", ("-Q", "udev-hid-bpf")),
        ("dpkg-query", ("-W", "-f=${Package} ${Version}\n", "udev-hid-bpf")),
        ("rpm", ("-q", "udev-hid-bpf")),
    )
    for executable, arguments in queries:
        command = shutil.which(executable)
        if command is not None:
            return _run_command([command, *arguments])
    return None


def _parse_capability_bitmap(value: str) -> frozenset[int]:
    """Convert a Linux input sysfs bitmap into a set of event codes."""

    words = value.split()
    bits_per_word = 64 if sys.maxsize > 2**32 else 32
    codes: set[int] = set()
    for word_index, word in enumerate(reversed(words)):
        try:
            bitmap = int(word, 16)
        except ValueError:
            return frozenset()
        bit = 0
        while bitmap:
            if bitmap & 1:
                codes.add(word_index * bits_per_word + bit)
            bitmap >>= 1
            bit += 1
    return frozenset(codes)


def _input_devices_named(
    name_to_match: str,
    vendor_to_match: int,
    product_to_match: int,
    root: Path = INPUT_CLASS_ROOT,
    dev_root: Path = INPUT_DEVICE_ROOT,
) -> list[KeypadDevice]:
    if not root.exists():
        return []

    devices: list[KeypadDevice] = []
    for event in sorted(root.glob("event*")):
        try:
            name = (event / "device" / "name").read_text(
                encoding="utf-8", errors="replace"
            )
            relative = (event / "device" / "capabilities" / "rel").read_text(
                encoding="ascii", errors="replace"
            )
            vendor_id = int(
                (event / "device" / "id" / "vendor").read_text().strip(), 16
            )
            product_id = int(
                (event / "device" / "id" / "product").read_text().strip(), 16
            )
        except (OSError, ValueError):
            continue
        if (
            name.strip() != name_to_match
            or vendor_id != vendor_to_match
            or product_id != product_to_match
        ):
            continue
        devices.append(
            KeypadDevice(
                path=dev_root / event.name,
                sysfs_path=event,
                relative_codes=_parse_capability_bitmap(relative),
                vendor_id=vendor_id,
                product_id=product_id,
            )
        )
    return devices


def _keypad_devices(
    root: Path = INPUT_CLASS_ROOT,
    dev_root: Path = INPUT_DEVICE_ROOT,
) -> list[KeypadDevice]:
    return _input_devices_named(
        KEYPAD_NAME,
        KEYPAD_VENDOR_ID,
        KEYPAD_PRODUCT_ID,
        root,
        dev_root,
    )


def _virtual_pointer_devices(
    root: Path = INPUT_CLASS_ROOT,
    dev_root: Path = INPUT_DEVICE_ROOT,
) -> list[KeypadDevice]:
    return _input_devices_named(
        VIRTUAL_POINTER_NAME,
        VIRTUAL_VENDOR_ID,
        VIRTUAL_PRODUCT_ID,
        root,
        dev_root,
    )


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

    output = _run_command(command)
    if output is None:
        return {}
    return _parse_properties(output)


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

    runtime = runtime_environment()
    print(f"running kernel: {runtime.running_kernel}")
    print(f"Live ISO/archiso: {'yes' if runtime.live else 'no'}")
    if runtime.kernel_modules_match:
        print(f"matching kernel modules: {runtime.matching_module_directory}")
    else:
        print("matching kernel modules: NOT FOUND")
        print(
            "recovery: reboot into a kernel that has a matching /lib/modules "
            "directory, then rerun setup"
        )
        problems += 1

    try:
        vendor_device = find_vendor_hidraw()
    except DeviceDiscoveryError as error:
        print(f"hidraw fallback interface: NOT AVAILABLE ({error})")
    else:
        print(
            f"hidraw fallback interface: {vendor_device.path} "
            f"({vendor_device.descriptor_state.value})"
        )

    package = _udev_hid_bpf_package()
    print(f"udev-hid-bpf package: {package or 'NOT FOUND'}")
    if package is None:
        problems += 1

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

    bpf_installed = bool(package and installed and loader_rule and hwdb_files)
    if package is None:
        print("HID-BPF installation: NOT INSTALLED")
        print("recovery: install udev-hid-bpf, then run kamvas-bridge setup --apply")
    elif not bpf_installed:
        print("HID-BPF installation: INCOMPLETE")
        print("recovery: reinstall udev-hid-bpf and rerun setup")
    else:
        print("HID-BPF installation: READY")

    hid_devices = _gs1333_hid_devices()
    if hid_devices:
        print(f"GS1333 HID devices: {len(hid_devices)}")
        for device in hid_devices:
            matches = _bpf_match_properties(_udev_properties(path=device))
            if matches:
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
    print(f"HUION_FIRMWARE_ID property: {firmware_id or 'not visible on current hidraw'}")

    loaded = _matching_paths(BPF_PIN_ROOT)
    if loaded:
        print("GS1333 HID-BPF loaded: " + ", ".join(str(path) for path in loaded))
        print("HID-BPF runtime: LOADED")
    else:
        print("GS1333 HID-BPF loaded: NOT FOUND under /sys/fs/bpf/hid")
        print("HID-BPF runtime: NOT LOADED")
        problems += 1

    keypads = _keypad_devices()
    if not keypads:
        print(f"GS1333 Keypad: NOT FOUND ({KEYPAD_NAME})")
        if loaded:
            print(
                "recovery: physically unplug the Kamvas, wait two seconds, and "
                "reconnect it; then rerun doctor"
            )
        problems += 1
    else:
        keypad_ready = False
        for keypad in keypads:
            capabilities = [
                name
                for code, name in REL_CAPABILITY_NAMES.items()
                if code in keypad.relative_codes
            ]
            missing = REQUIRED_KEYPAD_REL_CODES - keypad.relative_codes
            print(f"GS1333 Keypad: {keypad.path} ({KEYPAD_NAME})")
            print(
                "GS1333 Keypad EV_REL: "
                + (", ".join(capabilities) if capabilities else "NONE")
            )
            if missing:
                missing_names = [REL_CAPABILITY_NAMES[code] for code in sorted(missing)]
                print("GS1333 Keypad missing: " + ", ".join(missing_names))
            else:
                keypad_ready = True
        if not keypad_ready:
            problems += 1

    if installed and loader_rule and hwdb_files and hid_devices and not loaded:
        print("recovery commands (not executed by doctor):")
        print("  sudo systemd-hwdb update")
        print("  sudo udevadm control --reload")
        print("  sudo udevadm trigger --subsystem-match=hid")
        print("then physically unplug/reconnect the Kamvas")
    if switcher is None or switcher_rule is None:
        print("next: install upstream huion-switcher and its 80-huion-switcher.rules file")

    upstream_problems = problems
    print(
        "upstream HID path: "
        + ("READY" if upstream_problems == 0 else "NOT READY")
    )

    remapper_problems = 0
    remapper_rule = _first_existing(REMAPPER_RULE_PATHS)
    modules_load = _first_existing(MODULES_LOAD_PATHS)
    print(f"kamvas-bridge udev rule: {remapper_rule or 'NOT FOUND'}")
    print(f"uinput modules-load config: {modules_load or 'NOT FOUND'}")
    if remapper_rule is None or modules_load is None:
        print("recovery: rerun kamvas-bridge setup --apply")
        remapper_problems += 1

    evdev_available = find_spec("evdev") is not None
    print(f"python-evdev: {'FOUND' if evdev_available else 'NOT FOUND'}")
    if not evdev_available:
        print("recovery: install python-evdev and restart the user service")
        remapper_problems += 1

    source_readable = any(os.access(keypad.path, os.R_OK) for keypad in keypads)
    print(f"GS1333 Keypad readable: {'yes' if source_readable else 'no'}")
    if keypads and not source_readable:
        print(
            "recovery: reinstall/reload 70-kamvas-bridge.rules and reconnect the tablet"
        )
        remapper_problems += 1

    uinput_writable = UINPUT_PATH.exists() and os.access(UINPUT_PATH, os.W_OK)
    print(f"uinput writable: {'yes' if uinput_writable else 'no'}")
    if not uinput_writable:
        if UINPUT_PATH.exists():
            print("recovery: reload the kamvas-bridge udev rule for /dev/uinput")
        else:
            print(
                "recovery: load the matching uinput module; if modules do not match, "
                "reboot before retrying"
            )
        remapper_problems += 1

    virtual_pointers = _virtual_pointer_devices()
    virtual_ready = any(
        REQUIRED_KEYPAD_REL_CODES <= pointer.relative_codes
        for pointer in virtual_pointers
    )
    if virtual_pointers:
        for pointer in virtual_pointers:
            print(f"virtual pointer: {pointer.path} ({VIRTUAL_POINTER_NAME})")
    else:
        print("virtual pointer: NOT FOUND")
    if not virtual_ready:
        remapper_problems += 1

    runtime_ready = remapper_problems == 0
    print("remapper runtime: " + ("READY" if runtime_ready else "NOT READY"))

    service = user_service_state()
    if not service.installed:
        service_label = "NOT INSTALLED"
    elif service.active:
        service_label = f"ACTIVE ({service.sub_state})"
    elif service.active_state == "failed":
        service_label = "FAILED"
    else:
        service_label = f"INACTIVE ({service.sub_state})"
    print(f"remapper service: {service_label}")
    print(f"remapper service enabled: {'yes' if service.enabled else 'no'}")
    service_ready = service.installed and service.enabled and service.active
    if not service_ready:
        if not service.installed:
            print("recovery: kamvas-bridge service install")
        elif service.active_state == "failed":
            print("recovery: kamvas-bridge service restart")
            print(f"logs: journalctl --user -u {SERVICE_NAME} -b --no-pager")
        else:
            print("recovery: kamvas-bridge service enable")

    automatic_ready = runtime_ready and service_ready
    print("remapper: " + ("READY" if automatic_ready else "NOT READY"))

    hyprland = hyprland_status()
    hyprland_ready = True
    if not hyprland.detected:
        print("Hyprland mapping: NOT APPLICABLE (Hyprland not detected)")
    elif not hyprland.configured:
        print("Hyprland mapping: NOT CONFIGURED")
        print(
            "recovery: kamvas-bridge hyprland configure --output <MONITOR>; "
            "list outputs with hyprctl -j monitors"
        )
    else:
        print(f"Hyprland mapping output: {hyprland.output}")
        if not hyprland.session_active:
            print("Hyprland mapping: CONFIGURED (live session not available to verify)")
        else:
            print(
                f"Hyprland output active: {'yes' if hyprland.output_present else 'no'}"
            )
            print(
                f"Hyprland stylus {STYLUS_DEVICE_NAME}: "
                + ("FOUND" if hyprland.stylus_present else "NOT FOUND")
            )
            if hyprland.output_present and hyprland.stylus_present:
                print("Hyprland mapping: READY")
            elif hyprland.output_present and not hid_devices:
                print("Hyprland mapping: CONFIGURED (tablet disconnected)")
            else:
                hyprland_ready = False
                print("Hyprland mapping: NOT READY")

    return 0 if upstream_problems == 0 and automatic_ready and hyprland_ready else 1
