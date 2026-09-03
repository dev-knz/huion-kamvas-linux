"""Map normalized GS1333 evdev controls to safe configured actions."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path

from .actions import (
    EV_KEY,
    EV_REL,
    REL_HWHEEL,
    REL_WHEEL,
    ActionEmitter,
    ActionInvocation,
    SUPPORTED_KEY_CODES,
)
from .config import ConfigError, RemapperConfig, default_config, load_config, user_config_path
from .diagnostics import (
    VIRTUAL_KEYBOARD_NAME,
    VIRTUAL_KEYBOARD_PRODUCT_ID,
    VIRTUAL_POINTER_NAME,
    VIRTUAL_PRODUCT_ID,
    VIRTUAL_VENDOR_ID,
    _keypad_devices,
)

BTN_0 = 0x100
BTN_1 = 0x101
BTN_2 = 0x102
BTN_3 = 0x103
BTN_4 = 0x104
BTN_5 = 0x105
BTN_6 = 0x106
BTN_LEFT = 0x110

REL_X = 0x00
REL_Y = 0x01
REL_WHEEL_HI_RES = 0x0B
REL_HWHEEL_HI_RES = 0x0C

BUS_VIRTUAL = 0x06
BUTTON_NAMES_BY_CODE = {
    BTN_0: "BTN_0",
    BTN_1: "BTN_1",
    BTN_2: "BTN_2",
    BTN_3: "BTN_3",
    BTN_4: "BTN_4",
    BTN_5: "BTN_5",
    BTN_6: "BTN_6",
}


class RemapperError(RuntimeError):
    """Raised when the evdev/uinput remapper cannot start."""


class _TerminationRequested(Exception):
    """Internal clean shutdown requested by systemd."""


@dataclass(frozen=True, slots=True)
class EventTranslator:
    """Translate normalized physical events into configured action invocations."""

    config: RemapperConfig = field(default_factory=default_config)

    def translate(
        self, event_type: int, code: int, value: int
    ) -> ActionInvocation | None:
        if event_type == EV_KEY:
            button_name = BUTTON_NAMES_BY_CODE.get(code)
            # Shortcuts fire once on the physical press. Releases and kernel
            # repeat values do not create duplicate shortcut sequences.
            if button_name is None or value != 1:
                return None
            return ActionInvocation(self.config.buttons[button_name])

        if event_type != EV_REL or value == 0:
            return None
        if code == REL_WHEEL:
            dial = self.config.top_dial
        elif code == REL_HWHEEL:
            dial = self.config.bottom_dial
        else:
            # In particular, ignore the HI_RES companions to avoid two actions
            # for a single physical detent.
            return None
        action = dial.clockwise if value > 0 else dial.counterclockwise
        return ActionInvocation(action, repeat=abs(value))


async def _forward_device(
    path: Path,
    emitter: ActionEmitter,
    translator: EventTranslator,
    input_device_class: type,
) -> None:
    device = None
    try:
        device = input_device_class(str(path))
        print(f"GS1333 Keypad connected: {path}")
        async for event in device.async_read_loop():
            invocation = translator.translate(event.type, event.code, event.value)
            if invocation is not None:
                emitter.emit(invocation)
    except asyncio.CancelledError:
        raise
    except PermissionError as error:
        print(f"cannot read {path}: {error}; check the kamvas-bridge udev rule")
    except OSError as error:
        print(f"GS1333 Keypad/output unavailable: {path} ({error})")
    finally:
        if device is not None:
            device.close()


async def _hotplug_loop(
    emitter: ActionEmitter,
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
                    _forward_device(path, emitter, translator, input_device_class)
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


def _create_virtual_devices(uinput_class: type) -> tuple[object, object]:
    pointer = uinput_class(
        {
            EV_KEY: [BTN_LEFT],
            EV_REL: [REL_X, REL_Y, REL_WHEEL, REL_HWHEEL],
        },
        name=VIRTUAL_POINTER_NAME,
        bustype=BUS_VIRTUAL,
        vendor=VIRTUAL_VENDOR_ID,
        product=VIRTUAL_PRODUCT_ID,
        version=1,
    )
    try:
        keyboard = uinput_class(
            {EV_KEY: sorted(SUPPORTED_KEY_CODES)},
            name=VIRTUAL_KEYBOARD_NAME,
            bustype=BUS_VIRTUAL,
            vendor=VIRTUAL_VENDOR_ID,
            product=VIRTUAL_KEYBOARD_PRODUCT_ID,
            version=1,
        )
    except BaseException:
        pointer.close()
        raise
    return pointer, keyboard


def _request_termination(_signum: int, _frame: object) -> None:
    raise _TerminationRequested


def run_remapper(*, scan_interval: float = 1.0) -> int:
    """Run the hotplug-aware configured bridge until interrupted."""

    configuration_path = user_config_path()
    try:
        configuration = load_config(configuration_path)
    except ConfigError as error:
        raise RemapperError(f"invalid remapper config: {error}") from error

    try:
        from evdev import InputDevice, UInput, UInputError
    except ImportError as error:
        raise RemapperError(
            "python-evdev is required; run kamvas-bridge setup --apply"
        ) from error

    lock = _acquire_instance_lock()
    try:
        pointer, keyboard = _create_virtual_devices(UInput)
    except (FileNotFoundError, PermissionError, OSError, UInputError) as error:
        if lock is not None:
            lock.close()
        raise RemapperError(
            "cannot create the virtual pointer/keyboard; check /dev/uinput permissions"
        ) from error

    emitter = ActionEmitter(pointer, keyboard)
    config_source = configuration_path if configuration_path.exists() else "built-in defaults"
    print(f"remapper config: {config_source}")
    print(f"virtual pointer created: {pointer.device}")
    print(f"virtual keyboard created: {keyboard.device}")
    print("top dial -> vertical scroll; bottom dial -> zoom")

    previous_sigterm: object | None = None
    try:
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, _request_termination)
    except (OSError, ValueError):
        previous_sigterm = None

    try:
        asyncio.run(
            _hotplug_loop(
                emitter,
                EventTranslator(configuration),
                InputDevice,
                scan_interval=scan_interval,
            )
        )
    except _TerminationRequested:
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        keyboard.close()
        pointer.close()
        if lock is not None:
            lock.close()
    return 0
