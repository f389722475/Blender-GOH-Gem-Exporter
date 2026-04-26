# Installation Guide

## Blender Addon Install

1. Use the release asset `blender_goh_gem_exporter-1.1.0.zip`, or create a zip that contains the `blender_goh_gem_exporter` folder at the root.
2. Open Blender.
3. Go to `Edit > Preferences > Add-ons`.
4. Click `Install...`.
5. Select the addon zip.
6. Enable `GOH GEM Exporter`.

## Recommended Release Asset Layout

For GitHub releases, the most useful assets are:

- `blender_goh_gem_exporter-1.1.0.zip`
  Addon-only install zip containing:
  - `blender_goh_gem_exporter/__init__.py`
  - `blender_goh_gem_exporter/blender_exporter.py`
  - `blender_goh_gem_exporter/goh_core.py`
- `blender_goh_gem_exporter-1.1.0-full.zip`
  Source snapshot of the full repository, including English and Chinese README files, documentation, tests, and the sample `tests/1.blend` regression scene.

## Round-Trip Settings

Recommended export defaults for SOEdit and legacy Max-style workflows:

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`
- `Defer Basis Flip = On` when importing GOH-native models for Blender editing, so export-time ANM conversion keeps Blender, SOEdit, and game playback directions aligned
