# Blender GOH GEM Exporter

`Blender GOH GEM Exporter` is a Blender addon for `Call to Arms - Gates of Hell` and the GEM resource pipeline.

It focuses on practical round-trip work between Blender, SOEdit, and legacy 3ds Max GOH workflows while keeping the authoring experience Blender-native.

## Highlights

- Export `mdl`, `ply`, `mtl`, `vol`, and `anm`
- Import `anm` back into Blender
- Export visible meshes, skinned meshes, and mesh animation
- Export helper data for `Volume`, `Obstacle`, and `Area`
- Write inline primitive collision for `Box`, `Sphere`, and `Cylinder`
- Support `Basis` metadata, legacy Max text properties, and structured `goh_*` properties
- Provide Blender-side GOH panels for presets, basis metadata, transform blocks, and helper tools

## Repository Layout

- `blender_goh_gem_exporter/`
  Blender addon source
- `tests/`
  Smoke and Blender runtime regression tests
- `docs/`
  Installation notes, quick start guidance, and prerelease notes

## Supported Workflow Areas

### Geometry and Scene Export

- Visible mesh export as GOH `Bone` nodes
- `Armature + Vertex Groups` export for skinned `PLY`
- `LODView`, multi-`VolumeView`, and `{OFF}` support
- `Obstacle`, `Area`, and `Volume` helper export
- Inline primitive collision export for `Box`, `Sphere`, and `Cylinder`
- Automatic `.vol` splitting when polyhedron collision exceeds the 16-bit format limit

### Animation

- Object and bone transform animation export
- Mesh animation export and import
- `legacy`, `FRM2`, and `auto` animation writing
- Automatic chunk splitting for large mesh animation streams
- Sequence entries written back into `mdl`

### GOH-Specific Metadata

- Bone `Limits`, `Speed`, and `Speed2`
- Volume `Thickness`
- GOH material mainline parameters and texture option blocks
- `Basis` metadata with legacy-friendly header comments
- Transform block control with `Auto`, `Orientation`, and `Matrix34`

## Blender Panels

The addon installs the following GOH panels in `View3D > Sidebar > GOH`:

- `GOH Presets`
  Structured presets for visual meshes, dummy/placer helpers, collision volumes, obstacles, areas, and FX markers
- `GOH Basis`
  Blender-side replacement for MultiScript `Basis`
- `GOH Tools`
  Transform block tool, weapon helper shortcuts, and texture reporting
- `GOH Export`
  Import and export operators

## Legacy Max Compatibility

The exporter understands both Blender-style structured properties and old multi-line Max property buffers.

Supported legacy patterns include:

- `Poly`
- `CommonMesh`
- `Volume`
- `ID=...`
- `Type=...`
- `Model=...`
- `Wheelradius=...`
- `SteerMax=...`
- `Animation=...`
- `AnimationResume=...`
- `IKMin=...`
- `IKMax=...`
- `IKSpeed=...`
- `Support=...`
- `Radius=...`
- `Transform=Orientation|Matrix34|Position`

Compatibility rules:

- Structured `goh_*` fields always win
- Legacy text is used as fallback when structured fields are absent
- Old `ID` values can drive exported bone and volume names
- Old `IK*` keys are converted into GOH `Limits` and `Speed`

## Installation

### Blender Addon Install

1. Zip the `blender_goh_gem_exporter` folder by itself.
2. In Blender, open `Edit > Preferences > Add-ons > Install...`
3. Select the zip file.
4. Enable `GOH GEM Exporter`

For a cleaner release-ready package, see [docs/INSTALL.md](docs/INSTALL.md).

## Recommended Round-Trip Export Settings

For SOEdit and legacy Max-style round-trips:

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`

## Testing

The repository includes two regression layers:

- `tests/smoke_test.py`
  Core writer tests without launching Blender
- `tests/blender_runtime_test.py`
  Blender background export/import runtime test

Typical checks:

```powershell
python -X utf8 tests\smoke_test.py
```

```powershell
"D:\Steam\steamapps\common\Blender\blender.exe" -b --factory-startup --python tests\blender_runtime_test.py
```

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Quick Start](docs/QUICK_START.md)
- [Prerelease Notes](docs/RELEASE_NOTES_v0.8.0-pre1.md)

## License

This project is released under the [MIT License](LICENSE).
