import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kamvas_bridge.diagnostics import (
    _bpf_match_properties,
    _gs1333_hid_devices,
    _keypad_devices,
    _matching_hwdb_files,
    _matching_paths,
    _parse_capability_bitmap,
    _parse_properties,
    _udev_hid_bpf_package,
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

    def test_parses_keypad_relative_capabilities(self) -> None:
        capabilities = _parse_capability_bitmap("1940\n")

        self.assertTrue({6, 8, 11, 12} <= capabilities)

    def test_queries_udev_hid_bpf_package(self) -> None:
        with (
            patch(
                "kamvas_bridge.diagnostics.shutil.which",
                side_effect=lambda command: (
                    "/usr/bin/pacman" if command == "pacman" else None
                ),
            ),
            patch(
                "kamvas_bridge.diagnostics._run_command",
                return_value="udev-hid-bpf 2.3.0.20260703-2",
            ) as run_command,
        ):
            package = _udev_hid_bpf_package()

        self.assertEqual(package, "udev-hid-bpf 2.3.0.20260703-2")
        run_command.assert_called_once_with(
            ["/usr/bin/pacman", "-Q", "udev-hid-bpf"]
        )

    def test_finds_keypad_and_its_relative_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keypad = root / "event7" / "device"
            (keypad / "capabilities").mkdir(parents=True)
            (keypad / "name").write_text(
                "HUION Huion Tablet_GS1333 Keypad\n", encoding="utf-8"
            )
            (keypad / "capabilities" / "rel").write_text(
                "1940\n", encoding="ascii"
            )

            devices = _keypad_devices(root, Path("/test-input"))

            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0].path, Path("/test-input/event7"))
            self.assertTrue({6, 8, 11, 12} <= devices[0].relative_codes)


if __name__ == "__main__":
    unittest.main()
