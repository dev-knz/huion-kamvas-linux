"""Safe, reusable remapping actions and uinput emission."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol

EV_KEY = 0x01
EV_REL = 0x02

REL_HWHEEL = 0x06
REL_WHEEL = 0x08

KEY_ESC = 1
KEY_MINUS = 12
KEY_EQUAL = 13
KEY_BACKSPACE = 14
KEY_TAB = 15
KEY_ENTER = 28
KEY_LEFTCTRL = 29
KEY_LEFTSHIFT = 42
KEY_LEFTALT = 56
KEY_SPACE = 57
KEY_F1 = 59
KEY_F10 = 68
KEY_F11 = 87
KEY_F12 = 88
KEY_HOME = 102
KEY_UP = 103
KEY_PAGEUP = 104
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_END = 107
KEY_DOWN = 108
KEY_PAGEDOWN = 109
KEY_INSERT = 110
KEY_DELETE = 111
KEY_LEFTMETA = 125


class ActionError(ValueError):
    """Raised when a configured action is unsupported or malformed."""


@dataclass(frozen=True, slots=True)
class DisabledAction:
    """Consume a physical control without creating an output event."""


@dataclass(frozen=True, slots=True)
class ScrollAction:
    event_code: int
    value: int


@dataclass(frozen=True, slots=True)
class KeyboardShortcutAction:
    key_codes: tuple[int, ...]


Action = DisabledAction | ScrollAction | KeyboardShortcutAction


@dataclass(frozen=True, slots=True)
class ActionInvocation:
    action: Action
    repeat: int = 1

    def __post_init__(self) -> None:
        if self.repeat < 1:
            raise ValueError("action repeat must be at least one")


class UInputTarget(Protocol):
    def write(self, event_type: int, code: int, value: int) -> None: ...

    def syn(self) -> None: ...


_MODIFIER_CODES = {
    "ctrl": KEY_LEFTCTRL,
    "shift": KEY_LEFTSHIFT,
    "alt": KEY_LEFTALT,
    "super": KEY_LEFTMETA,
}
_MODIFIER_ALIASES = {
    "control": "ctrl",
    "meta": "super",
    "win": "super",
}
_MODIFIER_ORDER = ("ctrl", "shift", "alt", "super")

_KEY_CODES = {
    "escape": KEY_ESC,
    "minus": KEY_MINUS,
    "equal": KEY_EQUAL,
    "backspace": KEY_BACKSPACE,
    "tab": KEY_TAB,
    "enter": KEY_ENTER,
    "space": KEY_SPACE,
    "home": KEY_HOME,
    "up": KEY_UP,
    "pageup": KEY_PAGEUP,
    "left": KEY_LEFT,
    "right": KEY_RIGHT,
    "end": KEY_END,
    "down": KEY_DOWN,
    "pagedown": KEY_PAGEDOWN,
    "insert": KEY_INSERT,
    "delete": KEY_DELETE,
}
_KEY_ALIASES = {
    "esc": "escape",
    "return": "enter",
    "del": "delete",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "-": "minus",
    "=": "equal",
}

_KEY_CODES.update(zip("1234567890", range(2, 12), strict=True))
_KEY_CODES.update(zip("qwertyuiop", range(16, 26), strict=True))
_KEY_CODES.update(zip("asdfghjkl", range(30, 39), strict=True))
_KEY_CODES.update(zip("zxcvbnm", range(44, 51), strict=True))
_KEY_CODES.update({f"f{number}": KEY_F1 + number - 1 for number in range(1, 11)})
_KEY_CODES.update({"f11": KEY_F11, "f12": KEY_F12})

SUPPORTED_KEY_CODES = frozenset((*_MODIFIER_CODES.values(), *_KEY_CODES.values()))


def parse_keyboard_shortcut(value: str) -> KeyboardShortcutAction:
    """Parse modifiers plus exactly one safe keyboard key."""

    tokens = [token.strip().casefold() for token in value.split("+")]
    if not tokens or any(not token for token in tokens):
        raise ActionError(
            f"invalid shortcut {value!r}; separate key names with '+'"
        )

    modifiers: set[str] = set()
    normal_key: int | None = None
    for original in tokens:
        token = _MODIFIER_ALIASES.get(original, original)
        if token in _MODIFIER_CODES:
            if token in modifiers:
                raise ActionError(f"duplicate modifier {original!r} in {value!r}")
            modifiers.add(token)
            continue

        token = _KEY_ALIASES.get(token, token)
        key_code = _KEY_CODES.get(token)
        if key_code is None:
            raise ActionError(f"unknown key or action {original!r} in {value!r}")
        if normal_key is not None:
            raise ActionError(
                f"shortcut {value!r} must contain exactly one non-modifier key"
            )
        normal_key = key_code

    if normal_key is None:
        raise ActionError(
            f"shortcut {value!r} must contain one non-modifier key"
        )
    ordered_modifiers = tuple(
        _MODIFIER_CODES[name] for name in _MODIFIER_ORDER if name in modifiers
    )
    return KeyboardShortcutAction((*ordered_modifiers, normal_key))


_SPECIAL_ACTIONS: dict[str, Action] = {
    "disabled": DisabledAction(),
    # These signs preserve the existing REL_WHEEL pass-through behavior.
    "scroll_up": ScrollAction(REL_WHEEL, 1),
    "scroll_down": ScrollAction(REL_WHEEL, -1),
    "scroll_left": ScrollAction(REL_HWHEEL, -1),
    "scroll_right": ScrollAction(REL_HWHEEL, 1),
    "zoom_in": KeyboardShortcutAction((KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_EQUAL)),
    "zoom_out": KeyboardShortcutAction((KEY_LEFTCTRL, KEY_MINUS)),
}


def parse_action(value: str) -> Action:
    if not isinstance(value, str):
        raise ActionError("action must be a string")
    normalized = value.strip().casefold()
    if not normalized:
        raise ActionError("action cannot be empty")
    special = _SPECIAL_ACTIONS.get(normalized)
    return special if special is not None else parse_keyboard_shortcut(normalized)


@dataclass(slots=True)
class ActionEmitter:
    """Emit complete actions to separate pointer and keyboard devices."""

    pointer: UInputTarget
    keyboard: UInputTarget

    def emit(self, invocation: ActionInvocation) -> None:
        for _ in range(invocation.repeat):
            self._emit_once(invocation.action)

    def _emit_once(self, action: Action) -> None:
        if isinstance(action, DisabledAction):
            return
        if isinstance(action, ScrollAction):
            self.pointer.write(EV_REL, action.event_code, action.value)
            self.pointer.syn()
            return
        self._emit_keyboard(action)

    def _emit_keyboard(self, action: KeyboardShortcutAction) -> None:
        pressed: list[int] = []
        try:
            for key_code in action.key_codes:
                # Track before write so an asynchronous shutdown still attempts
                # a matching release for the key being emitted.
                pressed.append(key_code)
                self.keyboard.write(EV_KEY, key_code, 1)
            self.keyboard.syn()
        finally:
            active_error = sys.exception()
            release_error: Exception | None = None
            for key_code in reversed(pressed):
                try:
                    self.keyboard.write(EV_KEY, key_code, 0)
                except Exception as error:  # pragma: no cover - real device failure
                    release_error = release_error or error
            if pressed:
                try:
                    self.keyboard.syn()
                except Exception as error:  # pragma: no cover - real device failure
                    release_error = release_error or error
            if active_error is None and release_error is not None:
                raise release_error
