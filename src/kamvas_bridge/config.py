"""XDG-aware TOML configuration for physical controls and logical actions."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .actions import Action, ActionError, parse_action

BUTTON_NAMES = tuple(f"BTN_{number}" for number in range(7))
DIRECTION_NAMES = ("clockwise", "counterclockwise")

DEFAULT_ACTION_NAMES = {
    "buttons": {
        "BTN_0": "ctrl+z",
        "BTN_1": "disabled",
        "BTN_2": "disabled",
        "BTN_3": "disabled",
        "BTN_4": "disabled",
        "BTN_5": "disabled",
        "BTN_6": "disabled",
    },
    # Positive REL_WHEEL is clockwise in the existing GS1333 protocol model;
    # mapping it to scroll_up preserves the physically tested pass-through sign.
    "top_dial": {
        "clockwise": "scroll_up",
        "counterclockwise": "scroll_down",
    },
    "bottom_dial": {
        "clockwise": "zoom_in",
        "counterclockwise": "zoom_out",
    },
}

DEFAULT_CONFIG_TEXT = """# kamvas-bridge mappings
# Shortcuts are case-insensitive: modifiers joined with one key using '+'.

[buttons]
BTN_0 = "ctrl+z"
BTN_1 = "disabled"
BTN_2 = "disabled"
BTN_3 = "disabled"
BTN_4 = "disabled"
BTN_5 = "disabled"
BTN_6 = "disabled"

[top_dial]
# These defaults preserve the direction of the original scroll pass-through.
clockwise = "scroll_up"
counterclockwise = "scroll_down"

[bottom_dial]
clockwise = "zoom_in"
counterclockwise = "zoom_out"
"""


class ConfigError(ValueError):
    """Raised when the user configuration is unreadable or invalid."""


@dataclass(frozen=True, slots=True)
class DialMapping:
    clockwise: Action
    counterclockwise: Action


@dataclass(frozen=True, slots=True)
class RemapperConfig:
    buttons: Mapping[str, Action]
    top_dial: DialMapping
    bottom_dial: DialMapping


def user_config_path(
    *,
    home: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> Path:
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else home
    config_home = Path(environment.get("XDG_CONFIG_HOME", home / ".config"))
    return config_home / "kamvas-bridge" / "config.toml"


def _action(value: object, location: str) -> Action:
    if not isinstance(value, str):
        raise ConfigError(f"{location} must be a string action")
    try:
        return parse_action(value)
    except ActionError as error:
        raise ConfigError(f"{location}: {error}") from error


def _merged_table(
    document: dict[str, object], table_name: str, allowed: tuple[str, ...]
) -> dict[str, object]:
    raw = document.get(table_name, {})
    if not isinstance(raw, dict):
        raise ConfigError(f"[{table_name}] must be a TOML table")
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise ConfigError(
            f"unknown [{table_name}] setting(s): {', '.join(unknown)}"
        )
    merged: dict[str, object] = dict(DEFAULT_ACTION_NAMES[table_name])
    merged.update(raw)
    return merged


def parse_config(text: str, *, source: str = "config.toml") -> RemapperConfig:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{source}: invalid TOML: {error}") from error

    unknown_tables = sorted(set(document) - set(DEFAULT_ACTION_NAMES))
    if unknown_tables:
        raise ConfigError(f"{source}: unknown table(s): {', '.join(unknown_tables)}")

    buttons_raw = _merged_table(document, "buttons", BUTTON_NAMES)
    top_raw = _merged_table(document, "top_dial", DIRECTION_NAMES)
    bottom_raw = _merged_table(document, "bottom_dial", DIRECTION_NAMES)
    buttons = MappingProxyType(
        {
            name: _action(buttons_raw[name], f"{source} [buttons].{name}")
            for name in BUTTON_NAMES
        }
    )
    return RemapperConfig(
        buttons=buttons,
        top_dial=DialMapping(
            clockwise=_action(
                top_raw["clockwise"], f"{source} [top_dial].clockwise"
            ),
            counterclockwise=_action(
                top_raw["counterclockwise"],
                f"{source} [top_dial].counterclockwise",
            ),
        ),
        bottom_dial=DialMapping(
            clockwise=_action(
                bottom_raw["clockwise"], f"{source} [bottom_dial].clockwise"
            ),
            counterclockwise=_action(
                bottom_raw["counterclockwise"],
                f"{source} [bottom_dial].counterclockwise",
            ),
        ),
    )


def default_config() -> RemapperConfig:
    return parse_config(DEFAULT_CONFIG_TEXT, source="built-in defaults")


def load_config(path: Path | None = None) -> RemapperConfig:
    path = user_config_path() if path is None else path
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default_config()
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    return parse_config(text, source=str(path))


def ensure_user_config(path: Path | None = None) -> tuple[Path, bool]:
    """Create the documented defaults once, never replacing user content."""

    path = user_config_path() if path is None else path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(DEFAULT_CONFIG_TEXT)
    except FileExistsError:
        load_config(path)
        return path, False
    except OSError as error:
        raise ConfigError(f"cannot create {path}: {error}") from error
    return path, True
