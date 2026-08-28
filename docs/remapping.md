# Normalized dial remapping

The upstream path exposes the two physical dials as tablet-pad dials. This is
correct behavior, but browsers consume pointer scroll rather than
`TABLET_PAD_DIAL` events.

`kamvas-bridge remap` opens only the confirmed GS1333 Keypad evdev device and
creates `kamvas-bridge Virtual Pointer` through uinput:

| Source event | Virtual pointer event | Initial behavior |
| --- | --- | --- |
| `REL_WHEEL` ±1 | `REL_WHEEL` ±1 | dial 0, vertical scroll |
| `REL_HWHEEL` ±1 | `REL_HWHEEL` ±1 | dial 1, horizontal scroll |
| `REL_WHEEL_HI_RES` ±120 | ignored | companion of `REL_WHEEL` |
| `REL_HWHEEL_HI_RES` ±120 | ignored | companion of `REL_HWHEEL` |

Ignoring the high-resolution companions prevents one physical detent from
being emitted twice. The remapper does not contain a hidraw parser or debounce.

## Physically confirmed behavior

After `setup --apply` and a physical reconnect, the user service starts the
remapper automatically. Physical testing confirmed that dial 0 scrolls Firefox
vertically and dial 1 scrolls horizontally in applications that support a
horizontal axis.

Check both layers with:

```bash
PYTHONPATH=src python -m kamvas_bridge service status
PYTHONPATH=src python -m kamvas_bridge doctor
```

The complete working state reports `upstream HID path: READY`, an active and
enabled remapper service, and `remapper: READY`.

For debugging in the foreground, stop the persistent copy first:

```bash
PYTHONPATH=src python -m kamvas_bridge service disable
PYTHONPATH=src python -m kamvas_bridge remap
```

Enable it again after testing with `kamvas-bridge service enable`.

## Detection and hotplug

The source is selected dynamically using all of:

- input name `HUION Huion Tablet_GS1333 Keypad`;
- USB vendor `256c`;
- USB product `2008`.

No `/dev/input/eventN` number is stored. The running process rescans after
disconnects and attaches to the new event node. The virtual pointer has a
different name and virtual vendor/product IDs, so it cannot be selected as a
source and create a feedback loop.

The mapping table is isolated from device I/O. Future configuration can map
dials and buttons to different output actions without changing HID-BPF or
reintroducing vendor-report parsing.
