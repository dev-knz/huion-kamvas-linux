import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from kamvas_bridge.capture import capture


class CaptureTests(unittest.TestCase):
    def test_identical_reports_are_marked_but_not_dropped(self) -> None:
        report = bytes.fromhex("08 f1 01 01 00 01 00 00 00 00 00 00 00 00")

        with tempfile.NamedTemporaryFile(delete=False) as fixture:
            fixture.write(report + report)
            fixture_path = Path(fixture.name)

        try:
            output = io.StringIO()
            with redirect_stdout(output):
                parsed_count = capture(fixture_path, count=2)
        finally:
            fixture_path.unlink()

        self.assertEqual(parsed_count, 2)
        lines = output.getvalue().splitlines()
        self.assertIn("no TOP CLOCKWISE +1", lines[2])
        self.assertIn("yes TOP CLOCKWISE +1", lines[3])

    def test_end_of_stream_is_reported_instead_of_spinning(self) -> None:
        report = bytes.fromhex("08 f1 01 01 00 01 00 00 00 00 00 00 00 00")

        with tempfile.NamedTemporaryFile(delete=False) as fixture:
            fixture.write(report)
            fixture_path = Path(fixture.name)

        try:
            with redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(OSError, "EOF"):
                    capture(fixture_path, count=2)
        finally:
            fixture_path.unlink()


if __name__ == "__main__":
    unittest.main()
