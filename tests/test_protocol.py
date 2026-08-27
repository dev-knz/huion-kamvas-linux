import unittest

from kamvas_bridge.protocol import Dial, Direction, parse_vendor_dial_report


class VendorDialReportTests(unittest.TestCase):
    def test_top_clockwise(self) -> None:
        report = bytes.fromhex("08 f1 01 01 00 01 00 00 00 00 00 00 00 00")

        event = parse_vendor_dial_report(report)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.dial, Dial.TOP)
        self.assertEqual(event.direction, Direction.CLOCKWISE)
        self.assertEqual(event.relative_value, 1)

    def test_top_counterclockwise(self) -> None:
        report = bytes.fromhex("08 f1 01 01 00 02 00 00 00 00 00 00 00 00")

        event = parse_vendor_dial_report(report)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.dial, Dial.TOP)
        self.assertEqual(event.direction, Direction.COUNTERCLOCKWISE)
        self.assertEqual(event.relative_value, -1)

    def test_bottom_clockwise(self) -> None:
        report = bytes.fromhex("08 f1 01 02 00 01 00 00 00 00 00 00 00 00")

        event = parse_vendor_dial_report(report)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.dial, Dial.BOTTOM)
        self.assertEqual(event.direction, Direction.CLOCKWISE)

    def test_bottom_counterclockwise(self) -> None:
        report = bytes.fromhex("08 f1 01 02 00 02 00 00 00 00 00 00 00 00")

        event = parse_vendor_dial_report(report)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.dial, Dial.BOTTOM)
        self.assertEqual(event.direction, Direction.COUNTERCLOCKWISE)

    def test_unknown_report_is_ignored(self) -> None:
        report = bytes.fromhex("08 e1 01 01 00 01 00 00 00 00 00 00 00 00")

        self.assertIsNone(parse_vendor_dial_report(report))

    def test_unknown_dial_is_ignored(self) -> None:
        report = bytes.fromhex("08 f1 01 03 00 01 00 00 00 00 00 00 00 00")

        self.assertIsNone(parse_vendor_dial_report(report))

    def test_unknown_direction_is_ignored(self) -> None:
        report = bytes.fromhex("08 f1 01 01 00 03 00 00 00 00 00 00 00 00")

        self.assertIsNone(parse_vendor_dial_report(report))

    def test_wrong_length_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 14 bytes"):
            parse_vendor_dial_report(bytes.fromhex("08 f1 01"))


if __name__ == "__main__":
    unittest.main()
