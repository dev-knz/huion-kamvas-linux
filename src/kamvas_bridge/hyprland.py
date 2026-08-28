"""Persistent, reversible Hyprland mapping for the HID-BPF stylus device."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

STYLUS_DEVICE_NAME = "huion-huion-tablet_gs1333-stylus"
LUA_CONFIG_NAME = "hyprland.lua"
LEGACY_CONFIG_NAME = "hyprland.conf"
LUA_FRAGMENT_NAME = "kamvas_bridge.lua"
LEGACY_FRAGMENT_NAME = "kamvas-bridge.conf"
LUA_BEGIN = "-- BEGIN kamvas-bridge managed include"
LUA_END = "-- END kamvas-bridge managed include"
LEGACY_BEGIN = "# BEGIN kamvas-bridge managed include"
LEGACY_END = "# END kamvas-bridge managed include"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:+-]+$")


class HyprlandError(RuntimeError):
    """Raised when a safe persistent mapping cannot be configured."""


@dataclass(frozen=True, slots=True)
class HyprlandPaths:
    main: Path
    fragment: Path
    syntax: str


@dataclass(frozen=True, slots=True)
class HyprlandStatus:
    detected: bool
    configured: bool
    paths: HyprlandPaths | None
    output: str | None
    session_active: bool
    output_present: bool | None
    stylus_present: bool | None


def _config_home(
    *, home: Path | None = None, environment: dict[str, str] | None = None
) -> Path:
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else home
    return Path(environment.get("XDG_CONFIG_HOME", home / ".config")) / "hypr"


def hyprland_detected(
    *, home: Path | None = None, environment: dict[str, str] | None = None
) -> bool:
    environment = os.environ if environment is None else environment
    desktop = " ".join(
        (
            environment.get("XDG_CURRENT_DESKTOP", ""),
            environment.get("XDG_SESSION_DESKTOP", ""),
        )
    ).lower()
    config = _config_home(home=home, environment=environment)
    return bool(
        environment.get("HYPRLAND_INSTANCE_SIGNATURE")
        or "hyprland" in desktop
        or (config / LUA_CONFIG_NAME).is_file()
        or (config / LEGACY_CONFIG_NAME).is_file()
    )


def resolve_hyprland_paths(
    *,
    main_config: Path | None = None,
    home: Path | None = None,
    environment: dict[str, str] | None = None,
) -> HyprlandPaths:
    environment = os.environ if environment is None else environment
    config_home = _config_home(home=home, environment=environment)
    configured_path = environment.get("HYPRLAND_CONFIG")
    candidates: list[Path]
    if main_config is not None:
        candidates = [main_config]
    elif configured_path:
        candidates = [Path(configured_path).expanduser()]
    else:
        candidates = [config_home / LUA_CONFIG_NAME, config_home / LEGACY_CONFIG_NAME]

    main = next((path for path in candidates if path.is_file()), None)
    if main is None:
        expected = " or ".join(str(path) for path in candidates)
        raise HyprlandError(
            f"Hyprland configuration not found ({expected}); no file was created"
        )
    if main.suffix == ".lua":
        return HyprlandPaths(main, main.parent / LUA_FRAGMENT_NAME, "lua")
    return HyprlandPaths(main, main.parent / LEGACY_FRAGMENT_NAME, "hyprlang")


def _validate_identifier(value: str, label: str) -> str:
    if not value or SAFE_IDENTIFIER.fullmatch(value) is None:
        raise HyprlandError(
            f"invalid {label} {value!r}; use a connector name reported by hyprctl"
        )
    return value


def render_hyprland_fragment(
    output: str,
    *,
    device: str = STYLUS_DEVICE_NAME,
    syntax: str = "lua",
) -> str:
    output = _validate_identifier(output, "output")
    device = _validate_identifier(device, "tablet device")
    if syntax == "lua":
        return (
            "-- Managed by kamvas-bridge. Re-run the configure command to update.\n"
            "hl.device({\n"
            f"    name = {json.dumps(device)},\n"
            f"    output = {json.dumps(output)},\n"
            "})\n"
        )
    if syntax == "hyprlang":
        return (
            "# Managed by kamvas-bridge. Re-run the configure command to update.\n"
            "device {\n"
            f"    name = {device}\n"
            f"    output = {output}\n"
            "}\n"
        )
    raise HyprlandError(f"unsupported Hyprland configuration syntax: {syntax}")


def _include_block(paths: HyprlandPaths) -> tuple[str, str, str]:
    if paths.syntax == "lua":
        body = f'{LUA_BEGIN}\npcall(require, "kamvas_bridge")\n{LUA_END}'
        return LUA_BEGIN, LUA_END, body
    body = (
        f"{LEGACY_BEGIN}\nsource = {paths.fragment}\n{LEGACY_END}"
    )
    return LEGACY_BEGIN, LEGACY_END, body


def _replace_managed_block(text: str, begin: str, end: str, block: str | None) -> str:
    begin_index = text.find(begin)
    end_index = text.find(end)
    if (begin_index < 0) != (end_index < 0):
        raise HyprlandError("incomplete kamvas-bridge include block; refusing to edit")
    if begin_index >= 0:
        if end_index < begin_index:
            raise HyprlandError("invalid kamvas-bridge include block; refusing to edit")
        end_index += len(end)
        while end_index < len(text) and text[end_index] in "\r\n":
            end_index += 1
        before = text[:begin_index].rstrip()
        after = text[end_index:].lstrip("\r\n")
        text = before + ("\n\n" if before and after else "") + after
    text = text.rstrip()
    if block is not None:
        return (text + "\n\n" if text else "") + block + "\n"
    return text + ("\n" if text else "")


def _write_if_changed(path: Path, content: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    try:
        os.chmod(temporary, path.stat().st_mode & 0o7777)
    except OSError:
        pass
    os.replace(temporary, path)


def _run_hyprctl(arguments: list[str]) -> str | None:
    executable = shutil.which("hyprctl")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _json_names(arguments: list[str]) -> set[str]:
    output = _run_hyprctl(arguments)
    if output is None:
        return set()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return set()

    names: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str):
                names.add(name)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return names


def hyprland_monitors() -> set[str]:
    output = _run_hyprctl(["-j", "monitors"])
    if output is None:
        return set()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return set()
    if not isinstance(payload, list):
        return set()
    return {
        monitor["name"]
        for monitor in payload
        if isinstance(monitor, dict) and isinstance(monitor.get("name"), str)
    }


def hyprland_devices() -> set[str]:
    return _json_names(["-j", "devices"])


def configure_hyprland(
    output: str,
    *,
    device: str = STYLUS_DEVICE_NAME,
    main_config: Path | None = None,
    home: Path | None = None,
    environment: dict[str, str] | None = None,
    validate_live_output: bool = True,
) -> HyprlandPaths:
    paths = resolve_hyprland_paths(
        main_config=main_config, home=home, environment=environment
    )
    output = _validate_identifier(output, "output")
    monitors = hyprland_monitors() if validate_live_output else set()
    if monitors and output != "current" and output not in monitors:
        available = ", ".join(sorted(monitors))
        raise HyprlandError(f"output {output!r} not active; available: {available}")

    fragment = render_hyprland_fragment(
        output, device=device, syntax=paths.syntax
    )
    current = paths.main.read_text(encoding="utf-8", errors="replace")
    begin, end, block = _include_block(paths)
    updated = _replace_managed_block(current, begin, end, block)
    _write_if_changed(paths.fragment, fragment)
    _write_if_changed(paths.main, updated)
    _run_hyprctl(["reload"])
    return paths


def remove_hyprland_config(
    *,
    main_config: Path | None = None,
    home: Path | None = None,
    environment: dict[str, str] | None = None,
) -> HyprlandPaths:
    paths = resolve_hyprland_paths(
        main_config=main_config, home=home, environment=environment
    )
    current = paths.main.read_text(encoding="utf-8", errors="replace")
    begin, end, _ = _include_block(paths)
    updated = _replace_managed_block(current, begin, end, None)
    _write_if_changed(paths.main, updated)
    try:
        paths.fragment.unlink()
    except FileNotFoundError:
        pass
    _run_hyprctl(["reload"])
    return paths


def _configured_output(paths: HyprlandPaths) -> str | None:
    try:
        text = paths.fragment.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    quoted = re.search(r'output\s*=\s*"([A-Za-z0-9_.:+-]+)"', text)
    if quoted:
        return quoted.group(1)
    plain = re.search(r"output\s*=\s*([A-Za-z0-9_.:+-]+)", text)
    return plain.group(1) if plain else None


def hyprland_status(
    *,
    main_config: Path | None = None,
    home: Path | None = None,
    environment: dict[str, str] | None = None,
) -> HyprlandStatus:
    environment = os.environ if environment is None else environment
    detected = bool(main_config and main_config.is_file()) or hyprland_detected(
        home=home, environment=environment
    )
    if not detected:
        return HyprlandStatus(False, False, None, None, False, None, None)
    try:
        paths = resolve_hyprland_paths(
            main_config=main_config, home=home, environment=environment
        )
    except HyprlandError:
        return HyprlandStatus(True, False, None, None, False, None, None)

    try:
        main_text = paths.main.read_text(encoding="utf-8", errors="replace")
    except OSError:
        main_text = ""
    begin, end, _ = _include_block(paths)
    configured = paths.fragment.is_file() and begin in main_text and end in main_text
    output = _configured_output(paths) if configured else None
    session_active = bool(environment.get("HYPRLAND_INSTANCE_SIGNATURE"))
    monitors = hyprland_monitors() if session_active else set()
    devices = hyprland_devices() if session_active else set()
    output_present = (
        (output == "current" or output in monitors) if session_active and output else None
    )
    stylus_present = STYLUS_DEVICE_NAME in devices if session_active else None
    return HyprlandStatus(
        detected,
        configured,
        paths,
        output,
        session_active,
        output_present,
        stylus_present,
    )


def print_hyprland_status(*, main_config: Path | None = None) -> int:
    status = hyprland_status(main_config=main_config)
    if not status.detected:
        print("Hyprland: NOT DETECTED")
        return 0
    print(f"Hyprland mapping: {'CONFIGURED' if status.configured else 'NOT CONFIGURED'}")
    if status.paths is not None:
        print(f"main config: {status.paths.main}")
        print(f"managed fragment: {status.paths.fragment}")
    if status.output is not None:
        print(f"Kamvas output: {status.output}")
    if status.session_active:
        print(f"output active: {'yes' if status.output_present else 'no'}")
        print(f"GS1333 stylus visible: {'yes' if status.stylus_present else 'no'}")
    else:
        print("Hyprland session: not available for live verification")
    valid = status.configured and status.output_present is not False
    return 0 if valid else 1
