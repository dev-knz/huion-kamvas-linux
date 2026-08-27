"""Timestamp vendor reports without changing or suppressing input."""

from __future__ import annotations

import time
from pathlib import Path

from .protocol import REPORT_LENGTH, parse_vendor_dial_report


def capture(device: Path, count: int | None = None, include_unknown: bool = False) -> int:
    """Capture reports for duplicate analysis; return the parsed event count."""

    parsed_count = 0
    sequence = 0
    previous_report: bytes | None = None
    previous_time_ns: int | None = None
    start_ns = time.monotonic_ns()

    print(f"reading {device}; no reports will be discarded or deduplicated")
    print("seq elapsed_ms delta_ms adjacent_identical dial direction value raw")

    with device.open("rb", buffering=0) as stream:
        while count is None or parsed_count < count:
            report = stream.read(REPORT_LENGTH)
            now_ns = time.monotonic_ns()

            if not report:
                raise OSError("hidraw device returned EOF or was disconnected")
            if len(report) != REPORT_LENGTH:
                raise OSError(
                    f"short hidraw report: expected {REPORT_LENGTH} bytes, "
                    f"got {len(report)}"
                )

            event = parse_vendor_dial_report(report)
            if event is None and not include_unknown:
                # Keep adjacency and timing tied to the raw stream even when a
                # non-dial packet is omitted from the printed output.
                previous_report = report
                previous_time_ns = now_ns
                continue

            sequence += 1
            elapsed_ms = (now_ns - start_ns) / 1_000_000
            delta_ms = (
                "-"
                if previous_time_ns is None
                else f"{(now_ns - previous_time_ns) / 1_000_000:.3f}"
            )
            adjacent_identical = report == previous_report

            if event is None:
                dial = direction = value = "UNKNOWN"
            else:
                parsed_count += 1
                dial = event.dial.name
                direction = event.direction.name
                value = f"{event.relative_value:+d}"

            raw = " ".join(f"{byte:02x}" for byte in report)
            print(
                f"{sequence:04d} {elapsed_ms:.3f} {delta_ms} "
                f"{'yes' if adjacent_identical else 'no'} "
                f"{dial} {direction} {value} {raw}",
                flush=True,
            )

            previous_report = report
            previous_time_ns = now_ns

    return parsed_count
