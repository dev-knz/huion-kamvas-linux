"""Safe CachyOS/Arch setup for the confirmed upstream GS1333 path."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from .diagnostics import (
    BPF_FIRMWARE_ROOTS,
    HID_BPF_HWDB_ROOTS,
    HID_BPF_RULE_PATHS,
    HUION_SWITCHER_PATHS,
    HUION_SWITCHER_RULE_PATHS,
    _first_existing,
    _matching_hwdb_files,
    _matching_paths,
)

OS_RELEASE_PATH = Path("/etc/os-release")
HUION_SWITCHER_REPOSITORY = "https://github.com/whot/huion-switcher.git"
HUION_SWITCHER_BINARY_TARGET = PurePosixPath("/usr/lib/udev/huion-switcher")
HUION_SWITCHER_RULE_TARGET = PurePosixPath(
    "/etc/udev/rules.d/80-huion-switcher.rules"
)
PACKAGE_DATA_ROOT = Path(__file__).with_name("data")
REMAPPER_RULE_SOURCE = PACKAGE_DATA_ROOT / "70-kamvas-bridge.rules"
REMAPPER_RULE_TARGET = PurePosixPath("/etc/udev/rules.d/70-kamvas-bridge.rules")
MODULES_LOAD_SOURCE = PACKAGE_DATA_ROOT / "kamvas-bridge.conf"
MODULES_LOAD_TARGET = PurePosixPath("/etc/modules-load.d/kamvas-bridge.conf")

ARCH_PACKAGES = (
    "udev-hid-bpf",
    "bpf",
    "git",
    "base-devel",
    "rust",
    "pkgconf",
    "libusb",
    "systemd-libs",
    "python-evdev",
)


class SetupError(RuntimeError):
    """Raised when setup cannot safely continue."""


def _read_os_release(path: Path = OS_RELEASE_PATH) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    properties: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value.strip().strip('"')
    return properties


def _is_arch_family(properties: dict[str, str]) -> bool:
    distro_id = properties.get("ID", "").lower()
    distro_like = properties.get("ID_LIKE", "").lower().split()
    return distro_id in {"arch", "cachyos"} or "arch" in distro_like


def _switcher_installed() -> bool:
    return (
        _first_existing(HUION_SWITCHER_PATHS) is not None
        and _first_existing(HUION_SWITCHER_RULE_PATHS) is not None
    )


def _format_command(command: list[str]) -> str:
    return shlex.join(command)


def _print_plan(*, switcher_installed: bool) -> None:
    print("CachyOS/Arch setup plan:")
    step = 1
    print(
        f"  {step}. "
        + _format_command(
            ["sudo", "pacman", "-Syu", "--needed", *ARCH_PACKAGES]
        )
    )
    step += 1
    if switcher_installed:
        print(f"  {step}. keep the existing huion-switcher binary and udev rule")
        step += 1
    else:
        print(
            f"  {step}. clone and build {HUION_SWITCHER_REPOSITORY} "
            "as the current user"
        )
        step += 1
        print(f"  {step}. install {HUION_SWITCHER_BINARY_TARGET} with mode 0755")
        step += 1
        print(f"  {step}. install {HUION_SWITCHER_RULE_TARGET} with mode 0644")
        step += 1
    print(f"  {step}. install active-session permissions for GS1333 and uinput")
    step += 1
    print(f"  {step}. configure and load the uinput kernel module")
    step += 1
    print(f"  {step}. update the systemd hwdb and reload udev rules")
    step += 1
    print(f"  {step}. physically reconnect the tablet, then start the remapper")


def _run_checked(command: list[str], *, cwd: Path | None = None) -> None:
    print("+ " + _format_command(command))
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as error:
        raise SetupError(f"required command not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        raise SetupError(
            f"command failed with status {error.returncode}: {_format_command(command)}"
        ) from error


def _require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise SetupError(f"required command not found: {command}")


def _verify_packaged_bpf() -> None:
    objects = [
        path for root in BPF_FIRMWARE_ROOTS for path in _matching_paths(root)
    ]
    if not objects:
        raise SetupError(
            "udev-hid-bpf was installed but no Kamvas13Gen3 object was found"
        )
    if _first_existing(HID_BPF_RULE_PATHS) is None:
        raise SetupError("udev-hid-bpf was installed without its udev rule")
    if not _matching_hwdb_files(HID_BPF_HWDB_ROOTS):
        raise SetupError("udev-hid-bpf was installed without the GS1333 hwdb match")


def _install_switcher() -> None:
    with tempfile.TemporaryDirectory(prefix="kamvas-bridge-") as directory:
        source = Path(directory) / "huion-switcher"
        _run_checked(
            ["git", "clone", "--depth", "1", HUION_SWITCHER_REPOSITORY, str(source)]
        )
        _run_checked(["cargo", "build", "--release", "--locked"], cwd=source)
        _run_checked(
            [
                "sudo",
                "install",
                "-Dm755",
                str(source / "target" / "release" / "huion-switcher"),
                str(HUION_SWITCHER_BINARY_TARGET),
            ]
        )
        _run_checked(
            [
                "sudo",
                "install",
                "-Dm644",
                str(source / "80-huion-switcher.rules"),
                str(HUION_SWITCHER_RULE_TARGET),
            ]
        )


def _install_remapper_runtime() -> None:
    for source in (REMAPPER_RULE_SOURCE, MODULES_LOAD_SOURCE):
        if not source.is_file():
            raise SetupError(f"packaged setup file not found: {source}")

    _run_checked(
        [
            "sudo",
            "install",
            "-Dm644",
            str(REMAPPER_RULE_SOURCE),
            str(REMAPPER_RULE_TARGET),
        ]
    )
    _run_checked(
        [
            "sudo",
            "install",
            "-Dm644",
            str(MODULES_LOAD_SOURCE),
            str(MODULES_LOAD_TARGET),
        ]
    )


def _confirm() -> bool:
    try:
        response = input("Apply this system setup? [y/N] ")
    except EOFError:
        return False
    return response.strip().lower() in {"y", "yes"}


def run_setup(*, apply: bool = False, assume_yes: bool = False) -> int:
    """Print or apply the CachyOS/Arch setup plan."""

    properties = _read_os_release()
    if not _is_arch_family(properties):
        distro = properties.get("PRETTY_NAME") or properties.get("ID") or "unknown"
        raise SetupError(
            f"automatic setup currently supports only CachyOS/Arch (detected: {distro})"
        )

    switcher_installed = _switcher_installed()
    _print_plan(switcher_installed=switcher_installed)
    if not apply:
        print("dry run only; no system changes were made")
        return 0

    if assume_yes is False and not _confirm():
        print("setup cancelled; no system changes were made")
        return 0

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise SetupError(
            "run setup as your normal user, without sudo; privileged steps request sudo"
        )

    _require_command("sudo")
    _require_command("pacman")
    _run_checked(["sudo", "pacman", "-Syu", "--needed", *ARCH_PACKAGES])
    _verify_packaged_bpf()

    if not switcher_installed:
        _require_command("git")
        _require_command("cargo")
        _install_switcher()

    _install_remapper_runtime()
    _run_checked(["sudo", "systemd-hwdb", "update"])
    _run_checked(["sudo", "udevadm", "control", "--reload"])
    _run_checked(["sudo", "modprobe", "uinput"])
    _run_checked(
        ["sudo", "udevadm", "trigger", "--action=add", "/sys/class/misc/uinput"]
    )
    _run_checked(["sudo", "udevadm", "settle"])

    print("setup files installed successfully")
    print("next: physically unplug the tablet, wait two seconds, and reconnect it")
    print("then: PYTHONPATH=src python -m kamvas_bridge remap")
    return 0
