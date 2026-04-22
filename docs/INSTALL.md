# Installation Guide

## Blender Addon Install

1. Create a zip that contains the `blender_goh_gem_exporter` folder at the root.
2. Open Blender.
3. Go to `Edit > Preferences > Add-ons`.
4. Click `Install...`.
5. Select the addon zip.
6. Enable `GOH GEM Exporter`.

## Recommended Release Asset Layout

For GitHub releases, the most useful assets are:

- Source snapshot of the full repository
- Addon-only install zip containing:
  - `blender_goh_gem_exporter/__init__.py`
  - `blender_goh_gem_exporter/blender_exporter.py`
  - `blender_goh_gem_exporter/goh_core.py`

## Round-Trip Settings

Recommended export defaults for SOEdit and legacy Max-style workflows:

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`
