"""Command-line entry point for kamvas-bridge diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from .capture import capture
from .device import DeviceDiscoveryError, find_vendor_hidraw
from .diagnostics import doctor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kamvas-bridge",
        description="Huion Kamvas 13 Gen 3 input diagnostics",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="verify the upstream GS1333 input path")

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
