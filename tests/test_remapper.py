import unittest

from kamvas_bridge.actions import (
    ActionInvocation,
    DisabledAction,
    KeyboardShortcutAction,
    ScrollAction,
    parse_action,
)
from kamvas_bridge.config import parse_config
from kamvas_bridge.diagnostics import (
    VIRTUAL_KEYBOARD_NAME,
    VIRTUAL_KEYBOARD_PRODUCT_ID,
    VIRTUAL_POINTER_NAME,
    VIRTUAL_PRODUCT_ID,
)
from kamvas_bridge.remapper import (
    BTN_0,
    BTN_1,
    BTN_6,
    BTN_LEFT,
    EV_KEY,
    EV_REL,
    REL_HWHEEL,
    REL_HWHEEL_HI_RES,
    REL_WHEEL,
    REL_WHEEL_HI_RES,
    EventTranslator,
    _create_virtual_devices,
)


class FakeUInput:
    instances: list["FakeUInput"] = []

    def __init__(self, capabilities: dict[int, list[int]], **properties: object):
        self.capabilities = capabilities
        self.properties = properties
        self.device = f"/dev/input/event{len(self.instances)}"
        self.closed = False
        self.instances.append(self)

    def close(self) -> None:
        self.closed = True


class RemapperTests(unittest.TestCase):
    def test_maps_positive_and_negative_top_dial_without_reversing_sign(self) -> None:
        translator = EventTranslator()

        positive = translator.translate(EV_REL, REL_WHEEL, 1)
        negative = translator.translate(EV_REL, REL_WHEEL, -1)

        self.assertEqual(positive, ActionInvocation(ScrollAction(REL_WHEEL, 1)))
        self.assertEqual(negative, ActionInvocation(ScrollAction(REL_WHEEL, -1)))

    def test_maps_bottom_dial_to_zoom(self) -> None:
        translator = EventTranslator()

        positive = translator.translate(EV_REL, REL_HWHEEL, 1)
        negative = translator.translate(EV_REL, REL_HWHEEL, -1)

        self.assertEqual(positive, ActionInvocation(parse_action("zoom_in")))
        self.assertEqual(negative, ActionInvocation(parse_action("zoom_out")))

    def test_ignores_high_resolution_companion_events(self) -> None:
        translator = EventTranslator()

        self.assertIsNone(translator.translate(EV_REL, REL_WHEEL_HI_RES, 120))
        self.assertIsNone(translator.translate(EV_REL, REL_HWHEEL_HI_RES, -120))

    def test_btn_zero_runs_default_ctrl_z_only_on_press(self) -> None:
        translator = EventTranslator()

        pressed = translator.translate(EV_KEY, BTN_0, 1)

        self.assertEqual(pressed, ActionInvocation(parse_action("ctrl+z")))
        self.assertIsInstance(pressed.action, KeyboardShortcutAction)
        self.assertIsNone(translator.translate(EV_KEY, BTN_0, 0))
        self.assertIsNone(translator.translate(EV_KEY, BTN_0, 2))

    def test_disabled_buttons_are_consumed_without_output_action(self) -> None:
        invocation = EventTranslator().translate(EV_KEY, BTN_6, 1)

        self.assertIsNotNone(invocation)
        assert invocation is not None
        self.assertIsInstance(invocation.action, DisabledAction)

    def test_btn_zero_through_six_are_available(self) -> None:
        translator = EventTranslator()

        for code in range(BTN_0, BTN_6 + 1):
            with self.subTest(code=code):
                self.assertIsNotNone(translator.translate(EV_KEY, code, 1))

    def test_custom_button_mapping_is_used(self) -> None:
        config = parse_config('[buttons]\nBTN_1 = "alt+tab"\n')

        invocation = EventTranslator(config).translate(EV_KEY, BTN_1, 1)

        self.assertEqual(invocation, ActionInvocation(parse_action("alt+tab")))

    def test_unmapped_key_codes_are_ignored_including_btn_stylus(self) -> None:
        translator = EventTranslator()

        self.assertIsNone(translator.translate(EV_KEY, 0x14B, 1))
        self.assertIsNone(translator.translate(EV_KEY, 999, 1))

    def test_relative_event_magnitude_repeats_configured_action(self) -> None:
        invocation = EventTranslator().translate(EV_REL, REL_HWHEEL, 3)

        self.assertEqual(invocation, ActionInvocation(parse_action("zoom_in"), repeat=3))

    def test_creates_separate_pointer_and_keyboard_devices(self) -> None:
        FakeUInput.instances = []

        pointer, keyboard = _create_virtual_devices(FakeUInput)

        self.assertIs(pointer, FakeUInput.instances[0])
        self.assertIs(keyboard, FakeUInput.instances[1])
        self.assertEqual(pointer.properties["name"], VIRTUAL_POINTER_NAME)
        self.assertEqual(pointer.properties["product"], VIRTUAL_PRODUCT_ID)
        self.assertEqual(keyboard.properties["name"], VIRTUAL_KEYBOARD_NAME)
        self.assertEqual(
            keyboard.properties["product"], VIRTUAL_KEYBOARD_PRODUCT_ID
        )
        self.assertNotEqual(
            pointer.properties["product"], keyboard.properties["product"]
        )
        self.assertEqual(pointer.capabilities[EV_KEY], [BTN_LEFT])
        self.assertNotIn(EV_REL, keyboard.capabilities)


if __name__ == "__main__":
    unittest.main()
