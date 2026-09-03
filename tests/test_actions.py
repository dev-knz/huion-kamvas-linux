import unittest

from kamvas_bridge.actions import (
    EV_KEY,
    EV_REL,
    ActionEmitter,
    ActionError,
    ActionInvocation,
    DisabledAction,
    KEY_EQUAL,
    KEY_LEFTCTRL,
    KEY_LEFTSHIFT,
    KEY_MINUS,
    KeyboardShortcutAction,
    REL_WHEEL,
    parse_action,
    parse_keyboard_shortcut,
)


class FakeOutput:
    def __init__(self) -> None:
        self.events: list[tuple[int, int, int] | tuple[str]] = []

    def write(self, event_type: int, code: int, value: int) -> None:
        self.events.append((event_type, code, value))

    def syn(self) -> None:
        self.events.append(("syn",))


class FailingKeyboard(FakeOutput):
    def write(self, event_type: int, code: int, value: int) -> None:
        super().write(event_type, code, value)
        if code == 44 and value == 1:
            raise OSError("simulated output failure")


class ActionTests(unittest.TestCase):
    def test_parses_case_insensitive_modifiers_and_one_key(self) -> None:
        shortcut = parse_keyboard_shortcut("Shift+CTRL+Z")

        self.assertEqual(
            shortcut,
            KeyboardShortcutAction((KEY_LEFTCTRL, KEY_LEFTSHIFT, 44)),
        )

    def test_supports_named_single_keys(self) -> None:
        self.assertIsInstance(parse_action("space"), KeyboardShortcutAction)
        self.assertIsInstance(parse_action("Escape"), KeyboardShortcutAction)

    def test_supports_documented_shortcut_examples(self) -> None:
        for value in (
            "ctrl+z",
            "ctrl+shift+z",
            "ctrl+s",
            "ctrl+c",
            "ctrl+v",
            "ctrl+a",
            "shift+x",
            "alt+tab",
            "space",
            "escape",
            "enter",
            "delete",
            "backspace",
            "tab",
        ):
            with self.subTest(value=value):
                self.assertIsInstance(parse_action(value), KeyboardShortcutAction)

    def test_rejects_unknown_or_unsafe_actions(self) -> None:
        with self.assertRaisesRegex(ActionError, "unknown key or action"):
            parse_action("rm -rf /home/user")

    def test_rejects_two_normal_keys(self) -> None:
        with self.assertRaisesRegex(ActionError, "exactly one non-modifier"):
            parse_action("ctrl+z+x")

    def test_ctrl_z_press_and_release_order(self) -> None:
        pointer = FakeOutput()
        keyboard = FakeOutput()
        emitter = ActionEmitter(pointer, keyboard)

        emitter.emit(ActionInvocation(parse_action("ctrl+z")))

        self.assertEqual(
            keyboard.events,
            [
                (EV_KEY, KEY_LEFTCTRL, 1),
                (EV_KEY, 44, 1),
                ("syn",),
                (EV_KEY, 44, 0),
                (EV_KEY, KEY_LEFTCTRL, 0),
                ("syn",),
            ],
        )
        self.assertEqual(pointer.events, [])

    def test_zoom_in_press_and_release_order(self) -> None:
        keyboard = FakeOutput()
        emitter = ActionEmitter(FakeOutput(), keyboard)

        emitter.emit(ActionInvocation(parse_action("zoom_in")))

        self.assertEqual(
            keyboard.events,
            [
                (EV_KEY, KEY_LEFTCTRL, 1),
                (EV_KEY, KEY_LEFTSHIFT, 1),
                (EV_KEY, KEY_EQUAL, 1),
                ("syn",),
                (EV_KEY, KEY_EQUAL, 0),
                (EV_KEY, KEY_LEFTSHIFT, 0),
                (EV_KEY, KEY_LEFTCTRL, 0),
                ("syn",),
            ],
        )

    def test_zoom_out_press_and_release_order(self) -> None:
        keyboard = FakeOutput()
        emitter = ActionEmitter(FakeOutput(), keyboard)

        emitter.emit(ActionInvocation(parse_action("zoom_out")))

        self.assertEqual(
            keyboard.events,
            [
                (EV_KEY, KEY_LEFTCTRL, 1),
                (EV_KEY, KEY_MINUS, 1),
                ("syn",),
                (EV_KEY, KEY_MINUS, 0),
                (EV_KEY, KEY_LEFTCTRL, 0),
                ("syn",),
            ],
        )

    def test_disabled_action_emits_nothing(self) -> None:
        pointer = FakeOutput()
        keyboard = FakeOutput()

        ActionEmitter(pointer, keyboard).emit(ActionInvocation(DisabledAction()))

        self.assertEqual(pointer.events, [])
        self.assertEqual(keyboard.events, [])

    def test_scroll_action_uses_only_virtual_pointer(self) -> None:
        pointer = FakeOutput()
        keyboard = FakeOutput()

        ActionEmitter(pointer, keyboard).emit(
            ActionInvocation(parse_action("scroll_down"))
        )

        self.assertEqual(pointer.events, [(EV_REL, REL_WHEEL, -1), ("syn",)])
        self.assertEqual(keyboard.events, [])

    def test_pressed_modifiers_are_released_after_output_failure(self) -> None:
        keyboard = FailingKeyboard()

        with self.assertRaisesRegex(OSError, "simulated output failure"):
            ActionEmitter(FakeOutput(), keyboard).emit(
                ActionInvocation(parse_action("ctrl+z"))
            )

        self.assertIn((EV_KEY, 44, 0), keyboard.events)
        self.assertIn((EV_KEY, KEY_LEFTCTRL, 0), keyboard.events)


if __name__ == "__main__":
    unittest.main()
