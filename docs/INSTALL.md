# Installation Guide

## Blender Addon Install

1. Use the release asset `blender_goh_gem_exporter-1.3.2.zip`, or create a zip that contains the `blender_goh_gem_exporter` folder at the root.
2. Open Blender.
3. Go to `Edit > Preferences > Add-ons`.
4. Click `Install...`.
5. Select the addon zip.
6. Enable `GOH GEM Exporter`.

## Recommended Release Asset Layout

For GitHub releases, the most useful assets are:

- `blender_goh_gem_exporter-1.3.2.zip`
  Addon-only install zip containing the protected `blender_goh_gem_exporter` package at the zip root. Include every `.py` file in that package, including the modular subpackages under `core`, `formats`, `export`, `importers`, `tools`, and `ui`.
- `blender_goh_gem_exporter-1.3.2-full.zip`
  Protected repository snapshot for release review, including English and Chinese README files, documentation, tests, and the sample `tests/1.blend` and `tests/2.blend` regression scenes. The unprotected source mirror is kept locally in `Blender GOH Gem Exporter Unlock`.

## Collision Cage Generator

`Auto Collision Cage Volume` is fully built into the addon and has no external binary dependency.

The generator creates Blender-side watertight polyhedron helpers with validator metadata. Triangles and quads are legal, ngons are rejected, and a single helper can use up to `5000` faces. `Auto` chooses lengthwise loft profiles for large hull and turret sources, while gun barrels and smaller parts keep smoother rounded cages. `Optimize Iterations` defaults to `12` for interactive use and can be raised manually for deeper fitting; GOH `.vol` export still writes the final GEM-compatible volume data.

## Round-Trip Settings

Recommended export defaults for SOEdit and legacy Max-style workflows:

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`
- `Defer Basis Flip = Off` for source-faithful GOH-native model inspection that matches SOEdit/game hierarchy and helper placement
- `Defer Basis Flip = On` only when you intentionally want the legacy non-mirrored Blender editing parent; ANM import and export both apply the matching handedness compensation
