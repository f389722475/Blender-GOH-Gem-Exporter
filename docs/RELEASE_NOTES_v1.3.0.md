# Blender GOH GEM Exporter v1.3.0

Release date: 2026-04-28

This release is a structural refactor and packaging hardening pass. It keeps the 1.2.1 import/export, collision-cage, physics bake, and Basis/ANM behavior intact while making the codebase easier to maintain.

## Highlights

- `blender_exporter.py` was reduced below 5000 lines by moving major systems into focused modules.
- Export, model import, animation import, collision cage generation, physics bake, presets, and helper parsing now live in separate package modules.
- The local release zip protects the two internal algorithm modules under `blender_goh_gem_exporter/tools` while keeping the Blender addon install flow unchanged.

## Regression Coverage

- Python compile and smoke tests
- Blender runtime test
- issue #3 T26E4 import normals / Basis handedness probe
- `tests/2.blend` automatic collision cage scale regression
- Zip import/register/unregister test

## Recommended Release Assets

- `blender_goh_gem_exporter-1.3.0.zip`
  Addon install zip.
- `blender_goh_gem_exporter-1.3.0-full.zip`
  Protected repository snapshot with documentation, tests, and regression sample scenes.
