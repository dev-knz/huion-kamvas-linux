"""Parser for GS1333 vendor-mode dial reports observed on real hardware."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

REPORT_LENGTH = 14
VENDOR_REPORT_ID = 0x08
WHEEL_REPORT_BYTE = 0xF1
WHEEL_REPORT_MARKER = 0x01


class Dial(Enum):
    TOP = 0x01
    BOTTOM = 0x02


class Direction(Enum):
    CLOCKWISE = 0x01
    COUNTERCLOCKWISE = 0x02

    @property
    def relative_value(self) -> int:
        """Return the Linux relative-axis value chosen for this direction."""

        return 1 if self is Direction.CLOCKWISE else -1


@dataclass(frozen=True, slots=True)
class DialEvent:
    dial: Dial
    direction: Direction
    raw_report: bytes

    @property
    def relative_value(self) -> int:
        return self.direction.relative_value


def parse_vendor_dial_report(report: bytes) -> DialEvent | None:
    """Parse one confirmed 14-byte GS1333 vendor-mode dial report.

    ``None`` means the packet is either another report type or contains a value
    we have not mapped. Unknown bytes are intentionally not interpreted.

    A wrong packet length is a caller/read-boundary error and raises
    ``ValueError`` instead of being silently ignored.
    """

    if len(report) != REPORT_LENGTH:
        raise ValueError(f"expected {REPORT_LENGTH} bytes, got {len(report)}")

    if report[:3] != bytes(
        (VENDOR_REPORT_ID, WHEEL_REPORT_BYTE, WHEEL_REPORT_MARKER)
    ):
        return None

    try:
        dial = Dial(report[3])
        direction = Direction(report[5])
    except ValueError:
        return None

    return DialEvent(dial=dial, direction=direction, raw_report=bytes(report))
