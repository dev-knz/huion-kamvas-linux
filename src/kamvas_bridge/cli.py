"""Command-line entry point for kamvas-bridge diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from .capture import capture
from .device import DeviceDiscoveryError, find_vendor_hidraw
from .diagnostics import doctor
from .remapper import RemapperError, run_remapper
from .setup import SetupError, run_setup


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kamvas-bridge",
        description="Huion Kamvas 13 Gen 3 setup, diagnostics and dial remapping",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "doctor", help="verify upstream and remapper readiness"
    )
    subparsers.add_parser(
        "remap", help="translate GS1333 tablet-pad dials to pointer scrolling"
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
            return run_setup(apply=args.apply, assume_yes=args.yes)
        except SetupError as error:
            raise SystemExit(f"setup failed: {error}") from error

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
