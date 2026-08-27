import unittest

from kamvas_bridge.remapper import (
    EV_KEY,
    EV_REL,
    REL_HWHEEL,
    REL_HWHEEL_HI_RES,
    REL_WHEEL,
    REL_WHEEL_HI_RES,
    EventTranslator,
    OutputEvent,
    _emit,
)


class FakePointer:
    def __init__(self) -> None:
        self.events: list[tuple[int, int, int] | tuple[str]] = []

    def write(self, event_type: int, code: int, value: int) -> None:
        self.events.append((event_type, code, value))

    def syn(self) -> None:
        self.events.append(("syn",))


class RemapperTests(unittest.TestCase):
    def test_maps_top_dial_to_vertical_scroll(self) -> None:
        output = EventTranslator().translate(EV_REL, REL_WHEEL, -1)

        self.assertEqual(output, OutputEvent(EV_REL, REL_WHEEL, -1))

    def test_maps_bottom_dial_to_horizontal_scroll(self) -> None:
        output = EventTranslator().translate(EV_REL, REL_HWHEEL, 1)

        self.assertEqual(output, OutputEvent(EV_REL, REL_HWHEEL, 1))

    def test_ignores_high_resolution_companion_events(self) -> None:
        translator = EventTranslator()

        self.assertIsNone(translator.translate(EV_REL, REL_WHEEL_HI_RES, 120))
        self.assertIsNone(translator.translate(EV_REL, REL_HWHEEL_HI_RES, -120))

    def test_ignores_non_dial_events(self) -> None:
        self.assertIsNone(EventTranslator().translate(EV_KEY, 1, 1))

    def test_supports_future_custom_mapping(self) -> None:
        translator = EventTranslator({REL_HWHEEL: REL_WHEEL})

        output = translator.translate(EV_REL, REL_HWHEEL, -1)

        self.assertEqual(output, OutputEvent(EV_REL, REL_WHEEL, -1))

    def test_emits_one_output_event_and_sync(self) -> None:
        pointer = FakePointer()

        _emit(pointer, OutputEvent(EV_REL, REL_WHEEL, 1))

        self.assertEqual(pointer.events, [(EV_REL, REL_WHEEL, 1), ("syn",)])


if __name__ == "__main__":
    unittest.main()
