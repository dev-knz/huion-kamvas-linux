import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from kamvas_bridge.environment import RuntimeEnvironment
from kamvas_bridge.setup import (
    REMAPPER_RULE_SOURCE,
    SetupError,
    _is_arch_family,
    _install_remapper_runtime,
    _read_os_release,
    _verify_packaged_bpf,
    run_setup,
)

READY_ENVIRONMENT = RuntimeEnvironment(
    live=False,
    running_kernel="6.18.0-cachyos",
    matching_module_directory=Path("/usr/lib/modules/6.18.0-cachyos"),
)


class SetupTests(unittest.TestCase):
    def test_reads_cachyos_os_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "os-release"
            path.write_text(
                'NAME="CachyOS"\nID=cachyos\nID_LIKE="arch"\n',
                encoding="utf-8",
            )

            properties = _read_os_release(path)

        self.assertEqual(properties["ID"], "cachyos")
        self.assertTrue(_is_arch_family(properties))

    def test_rejects_unsupported_distribution(self) -> None:
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "other", "PRETTY_NAME": "Other Linux"},
            ),
            self.assertRaisesRegex(SetupError, "CachyOS/Arch"),
        ):
            run_setup()

    def test_dry_run_never_executes_commands(self) -> None:
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "cachyos"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=False),
            patch(
                "kamvas_bridge.setup.runtime_environment",
                return_value=READY_ENVIRONMENT,
            ),
            patch("kamvas_bridge.setup._run_checked") as run_checked,
            redirect_stdout(StringIO()),
        ):
            result = run_setup()

        self.assertEqual(result, 0)
        run_checked.assert_not_called()

    def test_apply_requires_confirmation(self) -> None:
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "arch"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=True),
            patch(
                "kamvas_bridge.setup.runtime_environment",
                return_value=READY_ENVIRONMENT,
            ),
            patch("kamvas_bridge.setup._confirm", return_value=False),
            patch("kamvas_bridge.setup._run_checked") as run_checked,
            redirect_stdout(StringIO()),
        ):
            result = run_setup(apply=True)

        self.assertEqual(result, 0)
        run_checked.assert_not_called()

    def test_apply_refuses_to_build_from_source_as_root(self) -> None:
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "cachyos"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=False),
            patch(
                "kamvas_bridge.setup.runtime_environment",
                return_value=READY_ENVIRONMENT,
            ),
            patch("kamvas_bridge.setup.os.geteuid", return_value=0, create=True),
            patch("kamvas_bridge.setup._run_checked") as run_checked,
            redirect_stdout(StringIO()),
            self.assertRaisesRegex(SetupError, "normal user"),
        ):
            run_setup(apply=True, assume_yes=True)

        run_checked.assert_not_called()

    def test_apply_runs_privileged_steps_after_explicit_consent(self) -> None:
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "cachyos"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=True),
            patch(
                "kamvas_bridge.setup.runtime_environment",
                return_value=READY_ENVIRONMENT,
            ),
            patch("kamvas_bridge.setup.os.geteuid", return_value=1000, create=True),
            patch("kamvas_bridge.setup._require_command"),
            patch("kamvas_bridge.setup._verify_packaged_bpf"),
            patch("kamvas_bridge.setup._install_remapper_runtime"),
            patch("kamvas_bridge.setup._preflight_hyprland"),
            patch(
                "kamvas_bridge.setup.configure_hyprland",
                return_value=SimpleNamespace(fragment=Path("/home/test/kamvas.lua")),
            ) as configure_hyprland,
            patch(
                "kamvas_bridge.setup.install_user_service",
                return_value=SimpleNamespace(unit=Path("/home/test/service")),
            ),
            patch("kamvas_bridge.setup.enable_user_service"),
            patch("kamvas_bridge.setup._run_checked") as run_checked,
            redirect_stdout(StringIO()),
        ):
            result = run_setup(
                apply=True,
                assume_yes=True,
                hyprland_output="HDMI-A-1",
            )

        self.assertEqual(result, 0)
        configure_hyprland.assert_called_once_with("HDMI-A-1")
        self.assertEqual(
            run_checked.call_args_list,
            [
                call(
                    [
                        "sudo",
                        "pacman",
                        "-Syu",
                        "--needed",
                        "udev-hid-bpf",
                        "bpf",
                        "git",
                        "base-devel",
                        "rust",
                        "pkgconf",
                        "libusb",
                        "systemd-libs",
                        "python-evdev",
                    ]
                ),
                call(["sudo", "systemd-hwdb", "update"]),
                call(["sudo", "udevadm", "control", "--reload"]),
                call(["sudo", "modprobe", "uinput"]),
                call(
                    [
                        "sudo",
                        "udevadm",
                        "trigger",
                        "--action=add",
                        "/sys/class/misc/uinput",
                    ]
                ),
                call(["sudo", "udevadm", "settle"]),
            ],
        )

    def test_apply_builds_switcher_when_it_is_missing(self) -> None:
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "arch"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=False),
            patch(
                "kamvas_bridge.setup.runtime_environment",
                return_value=READY_ENVIRONMENT,
            ),
            patch("kamvas_bridge.setup.os.geteuid", return_value=1000, create=True),
            patch("kamvas_bridge.setup._require_command"),
            patch("kamvas_bridge.setup._verify_packaged_bpf"),
            patch("kamvas_bridge.setup._install_remapper_runtime"),
            patch(
                "kamvas_bridge.setup.install_user_service",
                return_value=SimpleNamespace(unit=Path("/home/test/service")),
            ),
            patch("kamvas_bridge.setup.enable_user_service"),
            patch("kamvas_bridge.setup._run_checked"),
            patch("kamvas_bridge.setup._install_switcher") as install_switcher,
            redirect_stdout(StringIO()),
        ):
            result = run_setup(apply=True, assume_yes=True)

        self.assertEqual(result, 0)
        install_switcher.assert_called_once_with()

    def test_repeated_apply_updates_the_same_user_service(self) -> None:
        service_paths = SimpleNamespace(unit=Path("/home/test/service"))
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "cachyos"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=True),
            patch(
                "kamvas_bridge.setup.runtime_environment",
                return_value=READY_ENVIRONMENT,
            ),
            patch("kamvas_bridge.setup.os.geteuid", return_value=1000, create=True),
            patch("kamvas_bridge.setup._require_command"),
            patch("kamvas_bridge.setup._verify_packaged_bpf"),
            patch("kamvas_bridge.setup._install_remapper_runtime"),
            patch(
                "kamvas_bridge.setup.install_user_service",
                return_value=service_paths,
            ) as install_service,
            patch("kamvas_bridge.setup.enable_user_service") as enable_service,
            patch("kamvas_bridge.setup._run_checked"),
            redirect_stdout(StringIO()),
        ):
            first = run_setup(apply=True, assume_yes=True)
            second = run_setup(apply=True, assume_yes=True)

        self.assertEqual((first, second), (0, 0))
        self.assertEqual(install_service.call_count, 2)
        self.assertEqual(enable_service.call_count, 2)

    def test_live_environment_uses_selected_package_sync_not_full_upgrade(self) -> None:
        live = RuntimeEnvironment(
            live=True,
            running_kernel="6.18.0-cachyos-lts",
            matching_module_directory=Path("/usr/lib/modules/6.18.0-cachyos-lts"),
        )
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "cachyos"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=True),
            patch("kamvas_bridge.setup.runtime_environment", return_value=live),
            patch("kamvas_bridge.setup.os.geteuid", return_value=1000, create=True),
            patch("kamvas_bridge.setup._require_command"),
            patch("kamvas_bridge.setup._verify_packaged_bpf"),
            patch("kamvas_bridge.setup._install_remapper_runtime"),
            patch(
                "kamvas_bridge.setup.install_user_service",
                return_value=SimpleNamespace(unit=Path("/home/test/service")),
            ),
            patch("kamvas_bridge.setup.enable_user_service"),
            patch("kamvas_bridge.setup._run_checked") as run_checked,
            redirect_stdout(StringIO()),
        ):
            result = run_setup(apply=True, assume_yes=True)

        self.assertEqual(result, 0)
        package_command = run_checked.call_args_list[0].args[0]
        self.assertEqual(package_command[2], "-Sy")
        self.assertNotIn("-Syu", package_command)

    def test_kernel_module_mismatch_blocks_before_package_changes(self) -> None:
        mismatch = RuntimeEnvironment(
            live=True,
            running_kernel="6.18.0-cachyos-lts",
            matching_module_directory=None,
        )
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "cachyos"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=True),
            patch("kamvas_bridge.setup.runtime_environment", return_value=mismatch),
            patch("kamvas_bridge.setup._run_checked") as run_checked,
            redirect_stdout(StringIO()),
            self.assertRaisesRegex(SetupError, "kernel/modules mismatch"),
        ):
            run_setup(apply=True, assume_yes=True)

        run_checked.assert_not_called()

    def test_kernel_update_mismatch_stops_before_modprobe(self) -> None:
        mismatch = RuntimeEnvironment(
            live=False,
            running_kernel="6.18.0-cachyos",
            matching_module_directory=None,
        )
        with (
            patch(
                "kamvas_bridge.setup._read_os_release",
                return_value={"ID": "cachyos"},
            ),
            patch("kamvas_bridge.setup._switcher_installed", return_value=True),
            patch(
                "kamvas_bridge.setup.runtime_environment",
                side_effect=[READY_ENVIRONMENT, mismatch],
            ),
            patch("kamvas_bridge.setup.os.geteuid", return_value=1000, create=True),
            patch("kamvas_bridge.setup._require_command"),
            patch("kamvas_bridge.setup._verify_packaged_bpf"),
            patch("kamvas_bridge.setup._run_checked") as run_checked,
            redirect_stdout(StringIO()),
            self.assertRaisesRegex(SetupError, "kernel/modules mismatch"),
        ):
            run_setup(apply=True, assume_yes=True)

        self.assertEqual(len(run_checked.call_args_list), 1)
        self.assertIn("pacman", run_checked.call_args_list[0].args[0])

    def test_verifies_packaged_bpf_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = root / "firmware"
            rules = root / "rules"
            hwdb = root / "hwdb"
            firmware.mkdir()
            rules.mkdir()
            hwdb.mkdir()
            (firmware / "0010-Huion__Kamvas13Gen3.bpf.o").touch()
            rule = rules / "81-hid-bpf.rules"
            rule.touch()
            (hwdb / "81-hid-bpf-stable.hwdb").write_text(
                "hid-bpf:hid:b0003g*v0000256Cp00002008\n"
                " HID_BPF_S_001=0010-Huion__Kamvas13Gen3.bpf.o\n",
                encoding="utf-8",
            )

            with (
                patch("kamvas_bridge.setup.BPF_FIRMWARE_ROOTS", (firmware,)),
                patch("kamvas_bridge.setup.HID_BPF_RULE_PATHS", (rule,)),
                patch("kamvas_bridge.setup.HID_BPF_HWDB_ROOTS", (hwdb,)),
            ):
                _verify_packaged_bpf()

    def test_installs_packaged_remapper_permissions(self) -> None:
        with patch("kamvas_bridge.setup._run_checked") as run_checked:
            _install_remapper_runtime()

        self.assertEqual(len(run_checked.call_args_list), 2)
        first_command = run_checked.call_args_list[0].args[0]
        second_command = run_checked.call_args_list[1].args[0]
        self.assertEqual(first_command[:3], ["sudo", "install", "-Dm644"])
        self.assertEqual(first_command[-1], "/etc/udev/rules.d/70-kamvas-bridge.rules")
        self.assertEqual(second_command[:3], ["sudo", "install", "-Dm644"])
        self.assertEqual(
            second_command[-1], "/etc/modules-load.d/kamvas-bridge.conf"
        )

    def test_remapper_rule_covers_source_uinput_and_virtual_event(self) -> None:
        rule = REMAPPER_RULE_SOURCE.read_text(encoding="utf-8")

        self.assertIn("HUION Huion Tablet_GS1333 Keypad", rule)
        self.assertIn("kamvas-bridge Virtual Pointer", rule)
        self.assertIn('KERNEL=="uinput"', rule)
        self.assertNotIn('MODE="0666"', rule)


if __name__ == "__main__":
    unittest.main()
