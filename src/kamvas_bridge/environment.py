"""Detect Live ISO and running-kernel/module compatibility safely."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

LIVE_MARKERS = (
    Path("/run/archiso"),
    Path("/etc/mkinitcpio-archiso.conf"),
)
MODULE_ROOTS = (Path("/usr/lib/modules"), Path("/lib/modules"))


@dataclass(frozen=True, slots=True)
class RuntimeEnvironment:
    live: bool
    running_kernel: str
    matching_module_directory: Path | None

    @property
    def kernel_modules_match(self) -> bool:
        return self.matching_module_directory is not None


def is_live_environment(markers: tuple[Path, ...] = LIVE_MARKERS) -> bool:
    return any(marker.exists() for marker in markers)


def matching_kernel_module_directory(
    release: str,
    roots: tuple[Path, ...] = MODULE_ROOTS,
) -> Path | None:
    return next((root / release for root in roots if (root / release).is_dir()), None)


def runtime_environment(
    *,
    release: str | None = None,
    live_markers: tuple[Path, ...] = LIVE_MARKERS,
    module_roots: tuple[Path, ...] = MODULE_ROOTS,
) -> RuntimeEnvironment:
    release = platform.uname().release if release is None else release
    return RuntimeEnvironment(
        live=is_live_environment(live_markers),
        running_kernel=release,
        matching_module_directory=matching_kernel_module_directory(
            release, module_roots
        ),
    )
