import tempfile
import unittest
from pathlib import Path

from kamvas_bridge.environment import runtime_environment


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_detects_archiso_with_matching_kernel_modules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "run" / "archiso"
            modules = root / "modules"
            marker.mkdir(parents=True)
            (modules / "6.18.0-cachyos").mkdir(parents=True)

            status = runtime_environment(
                release="6.18.0-cachyos",
                live_markers=(marker,),
                module_roots=(modules,),
            )

        self.assertTrue(status.live)
        self.assertTrue(status.kernel_modules_match)

    def test_detects_running_kernel_module_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = root / "modules"
            (modules / "6.19.0-cachyos").mkdir(parents=True)

            status = runtime_environment(
                release="6.18.0-cachyos",
                live_markers=(root / "missing",),
                module_roots=(modules,),
            )

        self.assertFalse(status.live)
        self.assertFalse(status.kernel_modules_match)
        self.assertEqual(status.running_kernel, "6.18.0-cachyos")


if __name__ == "__main__":
    unittest.main()
