import unittest

from kamvas_bridge.cli import _parser


class CliTests(unittest.TestCase):
    def test_setup_accepts_explicit_hyprland_output(self) -> None:
        args = _parser().parse_args(
            ["setup", "--apply", "--hyprland-output", "HDMI-A-1"]
        )

        self.assertTrue(args.apply)
        self.assertEqual(args.hyprland_output, "HDMI-A-1")

    def test_service_actions_are_explicit(self) -> None:
        args = _parser().parse_args(["service", "status"])

        self.assertEqual(args.service_action, "status")

    def test_hyprland_configure_requires_output(self) -> None:
        args = _parser().parse_args(
            ["hyprland", "configure", "--output", "DP-2"]
        )

        self.assertEqual(args.hyprland_action, "configure")
        self.assertEqual(args.output, "DP-2")

    def test_config_validate_command(self) -> None:
        args = _parser().parse_args(["config", "validate"])

        self.assertEqual(args.config_action, "validate")


if __name__ == "__main__":
    unittest.main()
