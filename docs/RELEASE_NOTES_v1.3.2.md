# Blender GOH GEM Exporter v1.3.2

This maintenance release fixes the ANM handedness regression in the default GOH-native mirrored `basis` import path.

## Fixes

- ANM import now detects when a parent `basis` helper is still displayed as a mirrored GOH space in Blender and applies the same rotation/translation delta correction used for deferred basis editing.
- M60A1 `fire.anm` and Conqueror `fire_front.anm` now import with frame-12 `body` pitch matching SOEdit/game playback instead of visually pitching the hull downward in Blender.

## Validation

- Blender background M60A1 import/material/animation regression.
- Saved-scene reimport probes for `tests/m60a1.blend` and `tests/conquermk2.blend`.
- Random vehicle import regression over 12 vehicle samples for 5 iterations.
- Blender background runtime regression, Python compile, and addon smoke tests.

## Release Assets

- `blender_goh_gem_exporter-1.3.2.zip`
  Blender addon install package.
- `blender_goh_gem_exporter-1.3.2-full.zip`
  Protected source, docs, tests, and regression snapshot for release review.
