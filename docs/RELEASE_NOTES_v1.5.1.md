# Blender GOH GEM Exporter v1.5.1

This is a focused animation workflow release for GOH vehicle firing clips.

## Added

- One-click Eight Fire Directions bake preset for `fire_front`, `fire_fl`, `fire_left`, `fire_bl`, `fire_back`, `fire_br`, `fire_right`, and `fire_fr` clips.
- Fire trigger volume generator for basis-level `recoil_gun_*_vol` pie slices plus a turret-level `gun_recoil` helper point.
- `Body Sway Strength` and `Antenna Sway Strength` sliders for quick rebake tuning.
- `Antenna Mount` selector for body-mounted versus turret-mounted whip antennas.

## Fixed

- Directional barrel and turret-scoped parts now use a fixed local `X/-X` recoil stroke for every fire direction.
- Body recoil keeps the directional hull kick and recovery while turret and gun children stay local to the rotating turret.
- Antenna Whip directional polarity now bends the free tip toward `+X` / fire-forward reaction when the gun and hull recoil backward.
- Repeated fire-trigger generation keeps `recoil_gun_*_vol` volumes parented and aligned to `basis`, with `gun_recoil` Z aligned to the front trigger plane.
- FRM2 export now samples generated `GOH_AntennaWhip_*` shape keys through the single-key path even in older saved scenes missing role metadata, preventing stretched antenna mesh chunks.

## Recommended Install

Install:

- `blender_goh_gem_exporter-1.5.1.zip`

Archive/source review:

- `blender_goh_gem_exporter-1.5.1-full.zip`

## Verification

- `python -m compileall blender_goh_gem_exporter tests`
- `python tests\smoke_test.py`
- Blender runtime regression
- `tests\regression_3blend_export.py` with explicit FRM2 antenna mesh-animation bbox check
