"""Install and manage the unprivileged remapper systemd user service."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SERVICE_NAME = "kamvas-bridge.service"


class ServiceError(RuntimeError):
    """Raised when the managed user service cannot be changed."""


@dataclass(frozen=True, slots=True)
class UserServicePaths:
    unit: Path
    runtime_root: Path

    @property
    def package(self) -> Path:
        return self.runtime_root / "kamvas_bridge"


@dataclass(frozen=True, slots=True)
class ServiceState:
    installed: bool
    load_state: str
    unit_file_state: str
    active_state: str
    sub_state: str

    @property
    def enabled(self) -> bool:
        return self.unit_file_state in {"enabled", "enabled-runtime"}

    @property
    def active(self) -> bool:
        return self.active_state == "active"


def user_service_paths(
    *,
    home: Path | None = None,
    environment: dict[str, str] | None = None,
) -> UserServicePaths:
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else home
    config_home = Path(environment.get("XDG_CONFIG_HOME", home / ".config"))
    data_home = Path(environment.get("XDG_DATA_HOME", home / ".local" / "share"))
    return UserServicePaths(
        unit=config_home / "systemd" / "user" / SERVICE_NAME,
        runtime_root=data_home / "kamvas-bridge" / "runtime",
    )


def _unit_quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("systemd unit values cannot contain newlines")
    escaped = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_service_unit(
    runtime_root: Path,
    *,
    python_executable: Path | str = "/usr/bin/python",
) -> str:
    """Render a standalone unit that does not depend on the source checkout."""

    python = _unit_quote(str(python_executable))
    python_path = _unit_quote(f"PYTHONPATH={runtime_root}")
    return (
        "[Unit]\n"
        "Description=Huion Kamvas GS1333 dial remapper\n"
        "Documentation=https://github.com/dev-knz/huion-kamvas-linux\n"
        "StartLimitIntervalSec=60\n"
        "StartLimitBurst=5\n"
        "\n"
        "[Service]\n"
        "Type=exec\n"
        f"Environment={python_path}\n"
        f"ExecStart={python} -u -m kamvas_bridge remap\n"
        "Restart=on-failure\n"
        "RestartSec=3s\n"
        "NoNewPrivileges=yes\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _write_if_changed(path: Path, content: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
    return True


def install_user_service(
    *,
    paths: UserServicePaths | None = None,
    package_source: Path | None = None,
    python_executable: Path | str | None = None,
) -> UserServicePaths:
    """Install an idempotent user-owned runtime copy and unit file."""

    paths = user_service_paths() if paths is None else paths
    package_source = Path(__file__).parent if package_source is None else package_source
    if not (package_source / "__main__.py").is_file():
        raise ServiceError(f"kamvas-bridge package source not found: {package_source}")

    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    if package_source.resolve() != paths.package.resolve():
        shutil.copytree(
            package_source,
            paths.package,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    system_python = Path("/usr/bin/python")
    if python_executable is None:
        executable: Path | str = (
            system_python if system_python.is_file() else sys.executable
        )
    else:
        executable = python_executable
    _write_if_changed(
        paths.unit,
        render_service_unit(paths.runtime_root, python_executable=executable),
    )
    return paths


def _run_systemctl(arguments: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
    command = ["systemctl", "--user", *arguments]
    try:
        return subprocess.run(
            command,
            check=check,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as error:
        raise ServiceError("systemctl is required to manage the user service") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "unknown systemctl error").strip()
        raise ServiceError(f"systemctl --user failed: {detail}") from error
    except subprocess.TimeoutExpired as error:
        raise ServiceError("systemctl --user timed out") from error


def enable_user_service() -> None:
    _run_systemctl(["daemon-reload"], check=True)
    _run_systemctl(["enable", SERVICE_NAME], check=True)
    _run_systemctl(["restart", SERVICE_NAME], check=True)


def disable_user_service() -> None:
    result = _run_systemctl(["disable", "--now", SERVICE_NAME], check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown systemctl error").strip()
        raise ServiceError(f"could not stop/disable {SERVICE_NAME}: {detail}")


def restart_user_service() -> None:
    _run_systemctl(["daemon-reload"], check=True)
    _run_systemctl(["restart", SERVICE_NAME], check=True)


def user_service_state(
    *, unit_path: Path | None = None
) -> ServiceState:
    unit_path = user_service_paths().unit if unit_path is None else unit_path
    defaults = {
        "LoadState": "not-found",
        "UnitFileState": "disabled",
        "ActiveState": "inactive",
        "SubState": "dead",
    }
    try:
        result = _run_systemctl(
            [
                "show",
                SERVICE_NAME,
                "--property=LoadState,UnitFileState,ActiveState,SubState",
                "--no-pager",
            ],
            check=False,
        )
    except ServiceError:
        result = None
    if result is not None:
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in defaults:
                defaults[key] = value
    return ServiceState(
        installed=unit_path.is_file() or defaults["LoadState"] == "loaded",
        load_state=defaults["LoadState"],
        unit_file_state=defaults["UnitFileState"],
        active_state=defaults["ActiveState"],
        sub_state=defaults["SubState"],
    )


def uninstall_user_service(*, paths: UserServicePaths | None = None) -> None:
    """Remove only files owned by kamvas-bridge after an explicit request."""

    paths = user_service_paths() if paths is None else paths
    state = user_service_state(unit_path=paths.unit)
    if state.installed:
        disable_user_service()
    try:
        paths.unit.unlink()
    except FileNotFoundError:
        pass
    if paths.runtime_root.is_dir():
        shutil.rmtree(paths.runtime_root)
    _run_systemctl(["daemon-reload"], check=True)


def print_service_status() -> int:
    paths = user_service_paths()
    state = user_service_state(unit_path=paths.unit)
    print(f"unit file: {paths.unit if state.installed else 'NOT INSTALLED'}")
    print(f"enabled: {'yes' if state.enabled else 'no'}")
    print(f"active: {'yes' if state.active else 'no'}")
    print(f"systemd state: {state.active_state}/{state.sub_state}")
    return 0 if state.active else 1
