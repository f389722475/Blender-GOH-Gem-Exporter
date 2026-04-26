# Blender GOH GEM Exporter v1.0.1

Release date: 2026-04-26

This patch release focuses on making the `Antenna Whip` linked physics bake production-ready for tank cannon recoil while preserving the v1.0.0 import/export feature set.

## Highlights

- `Antenna Whip` now bakes rooted antenna mesh deformation through shape keys when possible.
- Sparse antenna meshes can be lengthwise subdivided before baking so the bend is visibly curved instead of a straight rotating rod.
- The antenna root remains fixed, with negative virtual-root values supported for starting the bend below the visible mesh.
- The bend uses the antenna principal axis and a constrained first-mode cantilever response for a single natural arc.
- The response length follows the source recoil frame count, so a 30-frame recoil drives the antenna inside that same timing window.
- The time response includes a stronger muzzle impulse and several damped front-back rebounds.
- Playback is smoother because generated antenna shape keys use linear interpolation and no longer include long static tails.
- Elongated source meshes such as cannon barrels are detected through their principal axis, keeping antenna sway aligned with the gun and vehicle front-back direction.

## Fixed

- Fixed stiff antenna bakes where the free tip stayed visually straight.
- Fixed `Antenna Root Anchor` and `Antenna Bend Segments` not taking effect consistently after rebakes.
- Fixed snake-like S-curves by keeping each frame as one rooted elastic arc.
- Fixed delayed antenna response where most visible motion happened after the source recoil clip.
- Fixed stepped playback caused by constant shape-key interpolation and repeated end-frame keys.
- Fixed sideways antenna sway caused by mismatched recoil axes on scenes where the cannon barrel mesh points along a different world axis.

## Recommended Release Assets

- `blender_goh_gem_exporter-1.0.1.zip`
  Install this in Blender through `Edit > Preferences > Add-ons > Install...`.
- `blender_goh_gem_exporter-1.0.1-full.zip`
  Full source, documentation, tests, and regression sample scenes.

## Validation

- `python -m py_compile blender_goh_gem_exporter\blender_exporter.py tests\blender_runtime_test.py`
- `python -X utf8 tests\smoke_test.py`
- Blender 5.1.1 background runtime regression test
- Manual regression with `tests/2.blend` for source-axis antenna sway
