# Configurable normalized-event remapping

The supported path consumes the GS1333 Keypad events already normalized by
upstream HID-BPF. It never decodes the vendor hidraw reports in the normal
remapper.

```text
physical evdev event
  -> logical button/dial direction
  -> action selected from config.toml
  -> separate uinput pointer or keyboard
  -> compositor/application
```

## Configuration lifecycle

The configuration is XDG-aware:

```text
$XDG_CONFIG_HOME/kamvas-bridge/config.toml
~/.config/kamvas-bridge/config.toml   # normal fallback
```

Setup creates a documented default with exclusive-create semantics. An
existing file is validated but never replaced. If the file is absent when the
remapper is run directly, the same internal defaults are used.

```bash
PYTHONPATH=src python -m kamvas_bridge config path
PYTHONPATH=src python -m kamvas_bridge config validate
```

After editing the file, reload it by restarting the existing user service:

```bash
PYTHONPATH=src python -m kamvas_bridge service restart
```

Live file watching is intentionally outside this iteration.

## Buttons

The five side buttons were observed from top to bottom as `BTN_0` through
`BTN_4`. The two dial-center buttons are `BTN_5` and `BTN_6`; the hardware
evidence does not yet identify which center corresponds to which number.

| Control | evdev code | Scan code | Default |
| --- | ---: | --- | --- |
| Top side button (`BTN_0`) | 256 | `90001` | `ctrl+z` |
| Second side button (`BTN_1`) | 257 | `90002` | `disabled` |
| Third side button (`BTN_2`) | 258 | `90003` | `disabled` |
| Fourth side button (`BTN_3`) | 259 | `90004` | `disabled` |
| Bottom side button (`BTN_4`) | 260 | `90005` | `disabled` |
| One dial-center button (`BTN_5`) | 261 | `90006` | `disabled` |
| Other dial-center button (`BTN_6`) | 262 | `90007` | `disabled` |

Only a physical press (`value=1`) invokes a shortcut. Release and repeat events
are ignored, so one press creates one complete shortcut. `BTN_STYLUS` is left
untouched.

## Dials

| Source event | Logical control | Default action |
| --- | --- | --- |
| positive `REL_WHEEL` | top clockwise | `scroll_up` |
| negative `REL_WHEEL` | top counterclockwise | `scroll_down` |
| positive `REL_HWHEEL` | bottom clockwise | `zoom_in` |
| negative `REL_HWHEEL` | bottom counterclockwise | `zoom_out` |
| `REL_WHEEL_HI_RES` | companion event | ignored |
| `REL_HWHEEL_HI_RES` | companion event | ignored |

The top defaults preserve the exact sign used by the already physically tested
pass-through implementation. The labels may therefore differ from a preferred
physical rotation direction; users can swap the two TOML values without code
changes.

HI_RES events remain ignored. Each detent therefore invokes only one action,
not both its normal and high-resolution reports.

## Actions and virtual devices

Special actions are:

```text
disabled
scroll_up  scroll_down  scroll_left  scroll_right
zoom_in    zoom_out
```

Other strings are parsed as a small generic keyboard chord: any reasonable
combination of `ctrl`, `shift`, `alt`, and `super`, plus exactly one supported
normal key. Parsing is case-insensitive. Letters, digits, `F1`–`F12`, common
navigation keys, and names including `space`, `escape`, `enter`, `tab`,
`backspace`, `delete`, `minus`, and `equal` are supported.

The pointer device exposes only pointer/scroll capabilities. A separate
`kamvas-bridge Virtual Keyboard` exposes the finite set of keyboard keys the
parser accepts. For each keyboard action, modifiers and the key are pressed in
order, synchronized, released in reverse order, and synchronized again. The
release path runs even if emission is interrupted.

No configured string is passed to a shell. Multiple normal keys, unknown keys,
unknown tables/settings, malformed TOML, arbitrary commands, and scripts are
rejected with a location-specific error.

## Hardware status

The upstream button codes and both dial event streams were observed on physical
GS1333 hardware. The top-dial virtual pointer scrolling was also confirmed in
real applications. The newly introduced BTN shortcut output, separate virtual
keyboard, and default bottom-dial zoom still require final physical validation
on CachyOS + Hyprland + Wayland.
