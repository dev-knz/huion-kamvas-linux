import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from kamvas_bridge.service import (
    SERVICE_NAME,
    ServiceState,
    UserServicePaths,
    enable_user_service,
    install_user_service,
    render_service_unit,
    uninstall_user_service,
    user_service_state,
)


class UserServiceTests(unittest.TestCase):
    def test_renders_restartable_unprivileged_user_unit(self) -> None:
        unit = render_service_unit(
            Path("/home/test/.local/share/kamvas-bridge/runtime"),
            python_executable="/usr/bin/python",
        )

        self.assertIn("Type=exec", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("NoNewPrivileges=yes", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertIn("-u -m kamvas_bridge remap", unit)
        self.assertNotIn("sudo", unit)

    def test_install_is_idempotent_and_independent_of_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "kamvas_bridge"
            source.mkdir(parents=True)
            (source / "__main__.py").write_text("pass\n", encoding="utf-8")
            (source / "remapper.py").write_text("VALUE = 1\n", encoding="utf-8")
            paths = UserServicePaths(
                unit=root / "config" / "systemd" / "user" / SERVICE_NAME,
                runtime_root=root / "data" / "kamvas-bridge" / "runtime",
            )

            install_user_service(
                paths=paths,
                package_source=source,
                python_executable="/usr/bin/python",
            )
            install_user_service(
                paths=paths,
                package_source=source,
                python_executable="/usr/bin/python",
            )

            self.assertTrue(paths.unit.is_file())
            self.assertEqual(
                (paths.package / "remapper.py").read_text(encoding="utf-8"),
                "VALUE = 1\n",
            )
            self.assertEqual(
                paths.unit.read_text(encoding="utf-8"),
                render_service_unit(
                    paths.runtime_root, python_executable="/usr/bin/python"
                ),
            )

    def test_enable_reloads_then_enables_now(self) -> None:
        with patch("kamvas_bridge.service._run_systemctl") as run_systemctl:
            enable_user_service()

        self.assertEqual(
            run_systemctl.call_args_list,
            [
                call(["daemon-reload"], check=True),
                call(["enable", SERVICE_NAME], check=True),
                call(["restart", SERVICE_NAME], check=True),
            ],
        )

    def test_reads_active_enabled_service_state(self) -> None:
        result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "LoadState=loaded\n"
                "UnitFileState=enabled\n"
                "ActiveState=active\n"
                "SubState=running\n"
            ),
            stderr="",
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("kamvas_bridge.service._run_systemctl", return_value=result),
        ):
            state = user_service_state(unit_path=Path(directory) / "missing")

        self.assertTrue(state.installed)
        self.assertTrue(state.enabled)
        self.assertTrue(state.active)

    def test_missing_service_is_inactive(self) -> None:
        result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="not found"
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("kamvas_bridge.service._run_systemctl", return_value=result),
        ):
            state = user_service_state(unit_path=Path(directory) / "missing")

        self.assertFalse(state.installed)
        self.assertFalse(state.enabled)
        self.assertFalse(state.active)

    def test_uninstall_removes_only_managed_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = UserServicePaths(
                unit=root / "config" / "systemd" / "user" / SERVICE_NAME,
                runtime_root=root / "data" / "kamvas-bridge" / "runtime",
            )
            paths.unit.parent.mkdir(parents=True)
            paths.unit.write_text("unit\n", encoding="utf-8")
            paths.package.mkdir(parents=True)
            (paths.package / "__main__.py").write_text("pass\n", encoding="utf-8")
            unrelated = root / "data" / "unrelated"
            unrelated.mkdir(parents=True)
            with (
                patch(
                    "kamvas_bridge.service.user_service_state",
                    return_value=ServiceState(
                        True, "loaded", "enabled", "active", "running"
                    ),
                ),
                patch("kamvas_bridge.service.disable_user_service") as disable,
                patch("kamvas_bridge.service._run_systemctl") as systemctl,
            ):
                uninstall_user_service(paths=paths)

            disable.assert_called_once_with()
            systemctl.assert_called_once_with(["daemon-reload"], check=True)
            self.assertFalse(paths.unit.exists())
            self.assertFalse(paths.runtime_root.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
