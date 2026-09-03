"""Command-line entry point for kamvas-bridge diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from .capture import capture
from .config import ConfigError, ensure_user_config, load_config, user_config_path
from .device import DeviceDiscoveryError, find_vendor_hidraw
from .diagnostics import doctor
from .hyprland import (
    HyprlandError,
    configure_hyprland,
    print_hyprland_status,
    remove_hyprland_config,
)
from .remapper import RemapperError, run_remapper
from .service import (
    ServiceError,
    disable_user_service,
    enable_user_service,
    install_user_service,
    print_service_status,
    restart_user_service,
    uninstall_user_service,
)
from .setup import SetupError, run_setup


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kamvas-bridge",
        description="Huion Kamvas 13 Gen 3 setup, diagnostics and control remapping",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "doctor", help="verify upstream and remapper readiness"
    )
    subparsers.add_parser(
        "remap", help="map normalized GS1333 buttons and dials to configured actions"
    )

    setup_parser = subparsers.add_parser(
        "setup", help="plan or apply CachyOS/Arch setup and permissions"
    )
    setup_mode = setup_parser.add_mutually_exclusive_group()
    setup_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="show the installation plan without changing the system (default)",
    )
    setup_mode.add_argument(
        "--apply",
        action="store_true",
        help="install packages, huion-switcher and udev configuration",
    )
    setup_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt; only valid with --apply",
    )
    setup_parser.add_argument(
        "--hyprland-output",
        metavar="OUTPUT",
        help="persistently map the HID-BPF stylus to this Hyprland output",
    )

    service_parser = subparsers.add_parser(
        "service", help="install, control or diagnose the systemd user service"
    )
    service_subparsers = service_parser.add_subparsers(
        dest="service_action", required=True
    )
    for action in ("install", "enable", "disable", "restart", "status", "uninstall"):
        service_subparsers.add_parser(action)

    hyprland_parser = subparsers.add_parser(
        "hyprland", help="configure or diagnose persistent stylus output mapping"
    )
    hyprland_subparsers = hyprland_parser.add_subparsers(
        dest="hyprland_action", required=True
    )
    configure_parser = hyprland_subparsers.add_parser("configure")
    configure_parser.add_argument("--output", required=True)
    configure_parser.add_argument("--config", type=Path)
    remove_parser = hyprland_subparsers.add_parser("remove")
    remove_parser.add_argument("--config", type=Path)
    status_parser = hyprland_subparsers.add_parser("status")
    status_parser.add_argument("--config", type=Path)

    config_parser = subparsers.add_parser(
        "config", help="locate or validate the remapper TOML configuration"
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_action", required=True
    )
    config_subparsers.add_parser("path")
    config_subparsers.add_parser("validate")

    capture_parser = subparsers.add_parser(
        "capture", help="timestamp vendor reports for duplicate analysis"
    )
    capture_parser.add_argument(
        "--device", type=Path, help="explicit hidraw path; otherwise auto-detect"
    )
    capture_parser.add_argument(
        "--count", type=int, help="stop after this many recognized dial reports"
    )
    capture_parser.add_argument(
        "--include-unknown", action="store_true", help="also print other 14-byte reports"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "doctor":
        return doctor()

    if args.command == "remap":
        try:
            return run_remapper()
        except RemapperError as error:
            raise SystemExit(f"remapper failed: {error}") from error

    if args.command == "setup":
        if args.yes and not args.apply:
            raise SystemExit("--yes requires --apply")
        try:
            return run_setup(
                apply=args.apply,
                assume_yes=args.yes,
                hyprland_output=args.hyprland_output,
            )
        except SetupError as error:
            raise SystemExit(f"setup failed: {error}") from error

    if args.command == "service":
        try:
            if args.service_action == "install":
                config_path, config_created = ensure_user_config()
                paths = install_user_service()
                enable_user_service()
                print(f"installed and enabled: {paths.unit}")
                print(
                    f"config {'created' if config_created else 'preserved'}: "
                    f"{config_path}"
                )
                return 0
            if args.service_action == "enable":
                enable_user_service()
                return 0
            if args.service_action == "disable":
                disable_user_service()
                return 0
            if args.service_action == "restart":
                restart_user_service()
                return 0
            if args.service_action == "uninstall":
                uninstall_user_service()
                print("kamvas-bridge user service removed")
                return 0
            return print_service_status()
        except ConfigError as error:
            raise SystemExit(f"service config failed: {error}") from error
        except ServiceError as error:
            raise SystemExit(f"service failed: {error}") from error

    if args.command == "hyprland":
        try:
            if args.hyprland_action == "configure":
                paths = configure_hyprland(
                    args.output, main_config=args.config
                )
                print(f"Hyprland mapping installed: {paths.fragment}")
                return 0
            if args.hyprland_action == "remove":
                paths = remove_hyprland_config(main_config=args.config)
                print(f"Hyprland mapping removed from: {paths.main}")
                return 0
            return print_hyprland_status(main_config=args.config)
        except HyprlandError as error:
            raise SystemExit(f"Hyprland configuration failed: {error}") from error

    if args.command == "config":
        path = user_config_path()
        if args.config_action == "path":
            print(path)
            return 0
        try:
            load_config(path)
        except ConfigError as error:
            raise SystemExit(f"remapper config: INVALID ({error})") from error
        if path.is_file():
            print(f"remapper config: READY ({path})")
        else:
            print(f"remapper config: READY (built-in defaults; expected path: {path})")
        return 0

    if args.count is not None and args.count < 1:
        raise SystemExit("--count must be greater than zero")

    try:
        device = args.device or find_vendor_hidraw(require_original=True).path
        capture(device, count=args.count, include_unknown=args.include_unknown)
    except (DeviceDiscoveryError, FileNotFoundError, PermissionError, OSError) as error:
        raise SystemExit(f"capture failed: {error}") from error
    except KeyboardInterrupt:
        return 130

    return 0
