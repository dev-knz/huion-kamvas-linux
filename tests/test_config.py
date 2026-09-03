import tempfile
import unittest
from pathlib import Path

from kamvas_bridge.actions import (
    DisabledAction,
    KeyboardShortcutAction,
    ScrollAction,
    parse_action,
)
from kamvas_bridge.config import (
    BUTTON_NAMES,
    ConfigError,
    default_config,
    ensure_user_config,
    load_config,
    parse_config,
    user_config_path,
)


class ConfigTests(unittest.TestCase):
    def test_defaults_cover_all_buttons_and_dials(self) -> None:
        config = default_config()

        self.assertEqual(tuple(config.buttons), BUTTON_NAMES)
        self.assertEqual(config.buttons["BTN_0"], parse_action("ctrl+z"))
        for name in BUTTON_NAMES[1:]:
            self.assertIsInstance(config.buttons[name], DisabledAction)
        self.assertEqual(config.top_dial.clockwise, ScrollAction(8, 1))
        self.assertEqual(config.top_dial.counterclockwise, ScrollAction(8, -1))
        self.assertEqual(config.bottom_dial.clockwise, parse_action("zoom_in"))
        self.assertEqual(
            config.bottom_dial.counterclockwise, parse_action("zoom_out")
        )

    def test_partial_toml_overrides_merge_with_defaults(self) -> None:
        config = parse_config(
            """
[buttons]
BTN_1 = "ctrl+shift+z"
BTN_4 = "space"

[bottom_dial]
clockwise = "scroll_right"
"""
        )

        self.assertEqual(config.buttons["BTN_1"], parse_action("ctrl+shift+z"))
        self.assertIsInstance(config.buttons["BTN_4"], KeyboardShortcutAction)
        self.assertIsInstance(config.buttons["BTN_6"], DisabledAction)
        self.assertEqual(config.bottom_dial.clockwise, parse_action("scroll_right"))
        self.assertEqual(
            config.bottom_dial.counterclockwise, parse_action("zoom_out")
        )

    def test_rejects_invalid_toml(self) -> None:
        with self.assertRaisesRegex(ConfigError, "invalid TOML"):
            parse_config("[buttons\nBTN_0 = 'ctrl+z'")

    def test_rejects_unknown_button(self) -> None:
        with self.assertRaisesRegex(ConfigError, "BTN_7"):
            parse_config('[buttons]\nBTN_7 = "ctrl+s"\n')

    def test_rejects_invalid_action_with_location(self) -> None:
        with self.assertRaisesRegex(ConfigError, r"\[buttons\]\.BTN_2"):
            parse_config('[buttons]\nBTN_2 = "launch firefox"\n')

    def test_uses_xdg_config_home(self) -> None:
        path = user_config_path(
            home=Path("/home/fallback"),
            environment={"XDG_CONFIG_HOME": "/custom/config"},
        )

        self.assertEqual(path, Path("/custom/config/kamvas-bridge/config.toml"))

    def test_missing_file_uses_internal_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = load_config(Path(directory) / "missing.toml")

        self.assertEqual(config, default_config())

    def test_repeated_setup_does_not_overwrite_user_config(self) -> None:
        custom = '[buttons]\nBTN_0 = "ctrl+s"\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kamvas-bridge" / "config.toml"
            first_path, first_created = ensure_user_config(path)
            path.write_text(custom, encoding="utf-8")
            second_path, second_created = ensure_user_config(path)

            preserved = path.read_text(encoding="utf-8")

        self.assertEqual(first_path, second_path)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(preserved, custom)


if __name__ == "__main__":
    unittest.main()
