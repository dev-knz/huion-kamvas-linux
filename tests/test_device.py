import tempfile
import unittest
from pathlib import Path

from kamvas_bridge.device import (
    DeviceDiscoveryError,
    GS1333_HID_ID,
    VENDOR_DESCRIPTOR_PREFIX,
    find_vendor_hidraw,
)


class DeviceDiscoveryTests(unittest.TestCase):
    def _add_hidraw(
        self,
        root: Path,
        name: str,
        hid_id: str,
        descriptor: bytes,
    ) -> None:
        device = root / name / "device"
        device.mkdir(parents=True)
        (device / "uevent").write_text(f"HID_ID={hid_id}\n", encoding="utf-8")
        (device / "report_descriptor").write_bytes(descriptor)

    def test_selects_vendor_interface_by_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._add_hidraw(root, "hidraw0", GS1333_HID_ID, b"pen")
            self._add_hidraw(
                root,
                "hidraw2",
                GS1333_HID_ID,
                VENDOR_DESCRIPTOR_PREFIX + bytes(27),
            )

            result = find_vendor_hidraw(root, Path("/test-dev"))

            self.assertEqual(result.path, Path("/test-dev/hidraw2"))

    def test_ignores_other_product_with_similar_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._add_hidraw(
                root,
                "hidraw0",
                "0003:0000256C:00002009",
                VENDOR_DESCRIPTOR_PREFIX + bytes(27),
            )

            with self.assertRaises(DeviceDiscoveryError):
                find_vendor_hidraw(root, Path("/test-dev"))

    def test_rejects_ambiguous_vendor_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("hidraw0", "hidraw1"):
                self._add_hidraw(
                    root,
                    name,
                    GS1333_HID_ID,
                    VENDOR_DESCRIPTOR_PREFIX + bytes(27),
                )

            with self.assertRaisesRegex(DeviceDiscoveryError, "multiple"):
                find_vendor_hidraw(root, Path("/test-dev"))


if __name__ == "__main__":
    unittest.main()
