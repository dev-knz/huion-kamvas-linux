import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from kamvas_bridge.config import ConfigError
from kamvas_bridge.device import DeviceDiscoveryError
from kamvas_bridge.diagnostics import (
    KeypadDevice,
    _bpf_match_properties,
    _gs1333_hid_devices,
    _keypad_devices,
    _matching_hwdb_files,
    _matching_paths,
    _parse_capability_bitmap,
    _parse_properties,
    _udev_hid_bpf_package,
    _virtual_keyboard_devices,
    _virtual_pointer_devices,
    doctor,
)
from kamvas_bridge.environment import RuntimeEnvironment
from kamvas_bridge.hyprland import HyprlandStatus
from kamvas_bridge.service import ServiceState


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
            (keypad / "capabilities" / "key").write_text(
                "7f 0 0 0 0\n", encoding="ascii"
            )
            (keypad / "id").mkdir()
            (keypad / "id" / "vendor").write_text("256c\n", encoding="ascii")
            (keypad / "id" / "product").write_text("2008\n", encoding="ascii")

            devices = _keypad_devices(root, Path("/test-input"))

            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0].path, Path("/test-input/event7"))
            self.assertTrue({6, 8, 11, 12} <= devices[0].relative_codes)
            self.assertTrue(set(range(256, 263)) <= devices[0].key_codes)

    def test_finds_virtual_pointer_without_matching_it_as_keypad(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pointer = root / "event30" / "device"
            (pointer / "capabilities").mkdir(parents=True)
            (pointer / "id").mkdir()
            (pointer / "name").write_text(
                "kamvas-bridge Virtual Pointer\n", encoding="utf-8"
            )
            (pointer / "capabilities" / "rel").write_text(
                "143\n", encoding="ascii"
            )
            (pointer / "id" / "vendor").write_text("1209\n", encoding="ascii")
            (pointer / "id" / "product").write_text("4b42\n", encoding="ascii")

            virtual = _virtual_pointer_devices(root, Path("/test-input"))
            keypads = _keypad_devices(root, Path("/test-input"))

            self.assertEqual(len(virtual), 1)
            self.assertEqual(virtual[0].path, Path("/test-input/event30"))
            self.assertEqual(keypads, [])

    def test_finds_virtual_keyboard_without_relative_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keyboard = root / "event31" / "device"
            (keyboard / "capabilities").mkdir(parents=True)
            (keyboard / "id").mkdir()
            (keyboard / "name").write_text(
                "kamvas-bridge Virtual Keyboard\n", encoding="utf-8"
            )
            (keyboard / "capabilities" / "key").write_text(
                "40000000\n", encoding="ascii"
            )
            (keyboard / "id" / "vendor").write_text("1209\n", encoding="ascii")
            (keyboard / "id" / "product").write_text("4b43\n", encoding="ascii")

            devices = _virtual_keyboard_devices(root, Path("/test-input"))

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].path, Path("/test-input/event31"))
        self.assertEqual(devices[0].relative_codes, frozenset())

    def _doctor_output(
        self,
        *,
        keypads: list[KeypadDevice],
        uinput_writable: bool,
        service: ServiceState,
        config_error: ConfigError | None = None,
    ) -> str:
        virtual = KeypadDevice(
            path=Path("/dev/input/event40"),
            sysfs_path=Path("/sys/class/input/event40"),
            relative_codes=frozenset((6, 8)),
            vendor_id=0x1209,
            product_id=0x4B42,
        )
        keyboard = KeypadDevice(
            path=Path("/dev/input/event41"),
            sysfs_path=Path("/sys/class/input/event41"),
            relative_codes=frozenset(),
            vendor_id=0x1209,
            product_id=0x4B43,
        )
        runtime = RuntimeEnvironment(
            live=False,
            running_kernel="6.18.0-cachyos",
            matching_module_directory=Path("/usr/lib/modules/6.18.0-cachyos"),
        )
        hyprland = HyprlandStatus(
            detected=False,
            configured=False,
            paths=None,
            output=None,
            session_active=False,
            output_present=None,
            stylus_present=None,
        )
        fake_uinput = Path("/dev/uinput")
        with (
            patch(
                "kamvas_bridge.diagnostics.find_vendor_hidraw",
                side_effect=DeviceDiscoveryError("not available"),
            ),
            patch("kamvas_bridge.diagnostics.runtime_environment", return_value=runtime),
            patch(
                "kamvas_bridge.diagnostics._udev_hid_bpf_package",
                return_value="udev-hid-bpf 2.3.0",
            ),
            patch(
                "kamvas_bridge.diagnostics._matching_paths",
                side_effect=lambda root: [root / "0010-Huion__Kamvas13Gen3.bpf.o"],
            ),
            patch(
                "kamvas_bridge.diagnostics._first_existing",
                return_value=Path("/installed"),
            ),
            patch(
                "kamvas_bridge.diagnostics._matching_hwdb_files",
                return_value=[Path("/installed/hid-bpf.hwdb")],
            ),
            patch(
                "kamvas_bridge.diagnostics._gs1333_hid_devices",
                return_value=[Path("/sys/bus/hid/devices/0003:256C:2008.0001")],
            ),
            patch(
                "kamvas_bridge.diagnostics._udev_properties",
                return_value={
                    "HID_BPF_S_001": "0010-Huion__Kamvas13Gen3.bpf.o"
                },
            ),
            patch("kamvas_bridge.diagnostics._keypad_devices", return_value=keypads),
            patch(
                "kamvas_bridge.diagnostics._virtual_pointer_devices",
                return_value=[virtual],
            ),
            patch(
                "kamvas_bridge.diagnostics._virtual_keyboard_devices",
                return_value=[keyboard],
            ),
            patch(
                "kamvas_bridge.diagnostics.load_config",
                side_effect=config_error,
            ),
            patch(
                "kamvas_bridge.diagnostics.user_config_path",
                return_value=Path("/home/test/config.toml"),
            ),
            patch("kamvas_bridge.diagnostics.find_spec", return_value=object()),
            patch("kamvas_bridge.diagnostics.UINPUT_PATH", fake_uinput),
            patch(
                "kamvas_bridge.diagnostics.os.access",
                side_effect=lambda path, mode: (
                    uinput_writable if path == fake_uinput else True
                ),
            ),
            patch.object(Path, "exists", return_value=uinput_writable),
            patch("kamvas_bridge.diagnostics.user_service_state", return_value=service),
            patch("kamvas_bridge.diagnostics.hyprland_status", return_value=hyprland),
            redirect_stdout(StringIO()) as output,
        ):
            doctor()
        return output.getvalue()

    def test_doctor_distinguishes_missing_keypad(self) -> None:
        service = ServiceState(True, "loaded", "enabled", "active", "running")

        output = self._doctor_output(
            keypads=[], uinput_writable=True, service=service
        )

        self.assertIn("GS1333 Keypad: NOT FOUND", output)
        self.assertIn("physically unplug the Kamvas", output)
        self.assertIn("upstream HID path: NOT READY", output)

    def test_doctor_distinguishes_uinput_and_inactive_service(self) -> None:
        keypad = KeypadDevice(
            path=Path("/dev/input/event27"),
            sysfs_path=Path("/sys/class/input/event27"),
            relative_codes=frozenset((6, 8, 11, 12)),
            vendor_id=0x256C,
            product_id=0x2008,
            key_codes=frozenset(range(256, 263)),
        )
        service = ServiceState(True, "loaded", "disabled", "inactive", "dead")

        output = self._doctor_output(
            keypads=[keypad], uinput_writable=False, service=service
        )

        self.assertIn("uinput writable: no", output)
        self.assertIn("remapper service: INACTIVE", output)
        self.assertIn("kamvas-bridge service enable", output)
        self.assertIn("remapper: NOT READY", output)

    def test_doctor_reports_invalid_remapper_config(self) -> None:
        keypad = KeypadDevice(
            path=Path("/dev/input/event27"),
            sysfs_path=Path("/sys/class/input/event27"),
            relative_codes=frozenset((6, 8, 11, 12)),
            vendor_id=0x256C,
            product_id=0x2008,
            key_codes=frozenset(range(256, 263)),
        )
        service = ServiceState(True, "loaded", "enabled", "active", "running")

        output = self._doctor_output(
            keypads=[keypad],
            uinput_writable=True,
            service=service,
            config_error=ConfigError("[buttons].BTN_0: unknown action"),
        )

        self.assertIn("remapper config: INVALID", output)
        self.assertIn("remapper: NOT READY", output)


if __name__ == "__main__":
    unittest.main()
