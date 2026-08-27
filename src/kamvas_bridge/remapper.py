"""Translate the upstream GS1333 evdev dials into a virtual pointer."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol

from .diagnostics import (
    VIRTUAL_POINTER_NAME,
    VIRTUAL_PRODUCT_ID,
    VIRTUAL_VENDOR_ID,
    _keypad_devices,
)

EV_KEY = 0x01
EV_REL = 0x02

BTN_LEFT = 0x110
REL_X = 0x00
REL_Y = 0x01
REL_HWHEEL = 0x06
REL_WHEEL = 0x08
REL_WHEEL_HI_RES = 0x0B
REL_HWHEEL_HI_RES = 0x0C

BUS_VIRTUAL = 0x06
DEFAULT_DIAL_MAPPING = {
    REL_WHEEL: REL_WHEEL,
    REL_HWHEEL: REL_HWHEEL,
}


class RemapperError(RuntimeError):
    """Raised when the evdev/uinput remapper cannot start."""


class VirtualPointer(Protocol):
    def write(self, event_type: int, code: int, value: int) -> None: ...

    def syn(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OutputEvent:
    event_type: int
    code: int
    value: int


@dataclass(frozen=True, slots=True)
class EventTranslator:
    """Translate normalized evdev codes without parsing vendor reports."""

    dial_mapping: Mapping[int, int] = field(
        default_factory=lambda: dict(DEFAULT_DIAL_MAPPING)
    )

    def translate(self, event_type: int, code: int, value: int) -> OutputEvent | None:
        if event_type != EV_REL or value == 0:
            return None

        output_code = self.dial_mapping.get(code)
        if output_code is None:
            return None
        return OutputEvent(EV_REL, output_code, value)


def _emit(pointer: VirtualPointer, event: OutputEvent) -> None:
    pointer.write(event.event_type, event.code, event.value)
    pointer.syn()


async def _forward_device(
    path: Path,
    pointer: VirtualPointer,
    translator: EventTranslator,
    input_device_class: type,
) -> None:
    device = None
    try:
        device = input_device_class(str(path))
        print(f"GS1333 Keypad connected: {path}")
        async for event in device.async_read_loop():
            output = translator.translate(event.type, event.code, event.value)
            if output is not None:
                _emit(pointer, output)
    except asyncio.CancelledError:
        raise
    except PermissionError as error:
        print(f"cannot read {path}: {error}; check the kamvas-bridge udev rule")
    except OSError as error:
        print(f"GS1333 Keypad disconnected: {path} ({error})")
    finally:
        if device is not None:
            device.close()


async def _hotplug_loop(
    pointer: VirtualPointer,
    translator: EventTranslator,
    input_device_class: type,
    *,
    scan_interval: float,
) -> None:
    tasks: dict[Path, asyncio.Task[None]] = {}
    waiting_printed = False

    try:
        while True:
            for path, task in list(tasks.items()):
                if task.done():
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        pass
                    del tasks[path]

            sources = {device.path for device in _keypad_devices()}
            for path in set(tasks) - sources:
                tasks[path].cancel()
            for path in sources - set(tasks):
                tasks[path] = asyncio.create_task(
                    _forward_device(path, pointer, translator, input_device_class)
                )

            if sources:
                waiting_printed = False
            elif not waiting_printed:
                print("waiting for HUION Huion Tablet_GS1333 Keypad")
                waiting_printed = True

            await asyncio.sleep(scan_interval)
    finally:
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)


def _acquire_instance_lock() -> object | None:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime is None:
        return None

    try:
        import fcntl

        lock = open(Path(runtime) / "kamvas-bridge-remapper.lock", "w")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ImportError) as error:
        raise RemapperError("another remapper instance is already running") from error
    return lock


def run_remapper(*, scan_interval: float = 1.0) -> int:
    """Run the hotplug-aware evdev to uinput bridge until interrupted."""

    try:
        from evdev import InputDevice, UInput, UInputError
    except ImportError as error:
        raise RemapperError(
            "python-evdev is required; run kamvas-bridge setup --apply"
        ) from error

    lock = _acquire_instance_lock()
    capabilities = {
        EV_KEY: [BTN_LEFT],
        EV_REL: [REL_X, REL_Y, REL_WHEEL, REL_HWHEEL],
    }
    try:
        pointer = UInput(
            capabilities,
            name=VIRTUAL_POINTER_NAME,
            bustype=BUS_VIRTUAL,
            vendor=VIRTUAL_VENDOR_ID,
            product=VIRTUAL_PRODUCT_ID,
            version=1,
        )
    except (FileNotFoundError, PermissionError, OSError, UInputError) as error:
        if lock is not None:
            lock.close()
        raise RemapperError(
            "cannot create the virtual pointer; check /dev/uinput permissions"
        ) from error

    print(f"virtual pointer created: {pointer.device}")
    print("dial 0 -> vertical scroll; dial 1 -> horizontal scroll")
    try:
        asyncio.run(
            _hotplug_loop(
                pointer,
                EventTranslator(),
                InputDevice,
                scan_interval=scan_interval,
            )
        )
    except KeyboardInterrupt:
        return 130
    finally:
        pointer.close()
        if lock is not None:
            lock.close()
    return 0
