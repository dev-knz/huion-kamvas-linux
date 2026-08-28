# Persistent Hyprland tablet mapping

The pen coordinate mapping is separate from dial scrolling. The exact
Hyprland device confirmed for the GS1333 stylus is:

```text
huion-huion-tablet_gs1333-stylus
```

Do not use the older guessed `...-pen` name.

## Configure

List the active connectors and choose the one displaying the tablet:

```bash
hyprctl monitors
```

Then save the mapping:

```bash
PYTHONPATH=src python -m kamvas_bridge hyprland configure \
  --output HDMI-A-1
```

`HDMI-A-1` is an example from the tested machine, not a global default. The
command validates the connector against the active Hyprland session before
editing files.

On current Hyprland Lua configuration, kamvas-bridge creates
`~/.config/hypr/kamvas_bridge.lua` with:

```lua
hl.device({
    name = "huion-huion-tablet_gs1333-stylus",
    output = "HDMI-A-1",
})
```

It adds one marked `pcall(require, "kamvas_bridge")` block to
`hyprland.lua`. On legacy configuration it creates `kamvas-bridge.conf` and
adds one marked `source` block to `hyprland.conf`. Existing personal settings
are preserved, repeated runs update the same fragment, and only the marked
block is owned by this project.

Setup can perform the same configuration in one operation:

```bash
PYTHONPATH=src python -m kamvas_bridge setup --apply \
  --hyprland-output HDMI-A-1
```

## Verify or change

```bash
PYTHONPATH=src python -m kamvas_bridge hyprland status
PYTHONPATH=src python -m kamvas_bridge doctor
PYTHONPATH=src python -m kamvas_bridge hyprland configure \
  --output DP-1
```

Status checks the saved connector, whether that output is currently active,
and whether the live Hyprland input-device list contains the exact stylus.

## Remove

```bash
PYTHONPATH=src python -m kamvas_bridge hyprland remove
```

Removal deletes the project-owned fragment and only the marked include block.
It does not rewrite or delete unrelated Hyprland configuration.
