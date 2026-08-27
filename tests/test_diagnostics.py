import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kamvas_bridge.diagnostics import (
    _bpf_match_properties,
    _gs1333_hid_devices,
    _matching_hwdb_files,
    _matching_paths,
    _parse_properties,
)


class DiagnosticHelpersTests(unittest.TestCase):
    def test_finds_both_compatibility_variants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "0009-Huion__Kamvas13Gen3.bpf.o",
                "0010-Huion__Kamvas13Gen3.bpf.o",
                "0010-Other__Device.bpf.o",
            ):
                (root / name).touch()

            matches = _matching_paths(root)

            self.assertEqual(len(matches), 2)

    def test_finds_hwdb_entry_for_gs1333(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "81-hid-bpf-stable.hwdb").write_text(
                "hid-bpf:hid:b0003g*v0000256Cp00002008\n"
                "  HID_BPF_S_001=0010-Huion__Kamvas13Gen3.bpf.o\n",
                encoding="utf-8",
            )
            (root / "81-hid-bpf-testing.hwdb").write_text(
                "hid-bpf:hid:b0003g*v00000001p00000002\n",
                encoding="utf-8",
            )

            matches = _matching_hwdb_files((root,))

            self.assertEqual(matches, [root / "81-hid-bpf-stable.hwdb"])

    def test_finds_all_gs1333_hid_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = [
                Path("/sys/bus/hid/devices") / name
                for name in (
                    "0003:256C:2008.0001",
                    "0003:256C:2008.0002",
                    "0003:256C:2008.0003",
                    "0003:256C:2009.0004",
                )
            ]

            with patch.object(Path, "iterdir", return_value=iter(candidates)):
                matches = _gs1333_hid_devices(root)

            self.assertEqual(len(matches), 3)

    def test_extracts_only_kamvas_bpf_properties(self) -> None:
        properties = _parse_properties(
            "HID_ID=0003:0000256C:00002008\n"
            "HID_BPF_S_004=0010-Huion__Kamvas13Gen3.bpf.o\n"
            "OTHER=value=with=equals\n"
        )

        matches = _bpf_match_properties(properties)

        self.assertEqual(
            matches,
            {"HID_BPF_S_004": "0010-Huion__Kamvas13Gen3.bpf.o"},
        )
        self.assertEqual(properties["OTHER"], "value=with=equals")


if __name__ == "__main__":
    unittest.main()
