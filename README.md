# Blender GOH GEM Exporter

[English](README.md) | [中文说明](README.zh-CN.md)

`Blender GOH GEM Exporter` is a Blender addon for `Call to Arms - Gates of Hell` and the GEM resource pipeline.

It focuses on practical round-trip work between Blender, SOEdit, and legacy 3ds Max GOH workflows while keeping the authoring experience Blender-native.

Current release: `1.3.0`.

## Highlights

- Export `mdl`, `ply`, `mtl`, `vol`, and `anm`
- Import `anm` back into Blender
- Import whole `.mdl` models with visual meshes, volumes, obstacles, and areas
- Export visible meshes, skinned meshes, and mesh animation
- Export helper data for `Volume`, `Obstacle`, and `Area`
- Write inline primitive collision for `Box`, `Sphere`, and `Cylinder`
- Support `Basis` metadata, legacy Max text properties, and structured `goh_*` properties
- Provide Blender-side GOH panels for presets, basis metadata, transform blocks, and helper tools
- Validate scenes before export and generate `GOH_Validation_Report.txt`
- Write `GOH_Export_Manifest.json` with file hashes and export counts
- Auto-fill GOH material texture fields from Blender image texture names
- Generate LOD file lists, bounds-based volume helpers, baked recoil actions, and directional fire clips
- Generate automatic topology-aware collision cage helpers from selected meshes using the built-in reward-guided Cage Fitter, including legal triangle/quad output, loft profile mode for hulls and turrets, configurable candidate scoring, and per-helper budgets up to 5000 faces
- Bake linked recoil, impact shake, and armor ripple mesh-animation effects
- `Antenna Whip` now bakes rooted antenna mesh deformation with a minimum-energy cubic beam curve, source-axis front-back sway, smooth linear shape-key playback, and natural long-tail recoil follow-through
- GOH model import now preserves source smoothing by applying EPLY normals as Blender custom split normals, and keeps default imported `basis` transforms faithful to SOEdit/game space
- Imported GOH `basis` mirror transforms can still be deferred for legacy non-mirrored editing; ANM import and export now share the same handness compensation so Blender, SOEdit, and in-game playback stay aligned

## Repository Layout

- `blender_goh_gem_exporter/`
  Blender addon source
- `tests/`
  Smoke and Blender runtime regression tests
- `docs/`
  Installation notes, quick start guidance, physics-bake notes, and release notes

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
  Transform block tool, weapon helper shortcuts, validation, material auto-fill, LOD helpers, collision helpers, physics bake presets, and texture reporting
- `GOH Export`
  Import and export operators for whole `.mdl` models and `.anm` animations

## GOH Validator

`View3D > Sidebar > GOH > GOH Tools > Validation` creates `GOH_Validation_Report.txt` and copies the report to the clipboard.

It checks common authoring mistakes:

- missing Basis metadata
- duplicate GOH export names
- mesh objects without material slots
- mesh objects with materials but no UV map
- empty meshes and zero-area faces
- unapplied mesh scale
- invalid LOD file names
- invalid `goh_volume_kind`
- missing cylinder primitive axis metadata
- missing volume bone targets
- invalid generated collision cage topology, including ngons, open edges, non-manifold edges, Euler mismatches, degenerate faces, skinny triangle warnings, and per-helper face-budget overflow
- invalid `Obstacle` / `Area` shape helper metadata
- overlapping multi-range `goh_sequence_ranges`
- materials without GOH texture fields
- missing image texture files

The validator is intentionally conservative.
It reports warnings for issues that may still export but should be inspected before opening the asset in SOEdit or the game.

## Authoring Helpers

`GOH Tools` now includes several production helpers:

- `Auto-Fill GOH Materials`
  infers `goh_diffuse`, `goh_bump`, `goh_specular`, `goh_lightmap`, `goh_mask`, and related texture fields from image texture node names
- `Assign LOD Files`
  writes `goh_lod_files` and optional `goh_lod_off` for selected visual meshes
- `Volume From Bounds`
  creates GOH volume helper objects from selected mesh bounding boxes
- `Auto Collision Cage Volume`
  creates closed, watertight polyhedron helpers from selected meshes. Triangles and quads are legal, ngons are rejected, and the per-helper face budget can be set up to `5000`. The generator uses template cages (`Box`, `Rounded Box`, `Quad Sphere`, `Loft Cage`, or `Auto`), OBB or ray-projection fitting, offset inflation, Taubin smoothing, quad planarization, topology validation, and a deterministic reward-guided optimizer. `Auto` uses lengthwise loft profiles for large body and turret parts so they can taper and follow sloped vehicle silhouettes.
- `Create Recoil Action`
  generates a baked local-axis recoil action and optional `goh_sequence_*` metadata
- `Assign Physics Link`
  stores a source-to-driven-part relationship for linked physics baking
- `Bake Linked Recoil`
  bakes a recoil source plus role-specific hull pendulum spring, anchored antenna whip mesh deformation with source-axis front-back sway, accessory jitter, follower, suspension bounce, or track rumble response into regular animation data
- `Bake Directional Set`
  records timeline clip ranges such as `fire_front`, `fire_back`, `fire_left`, and `fire_right`
- `Bake Impact Response`
  creates a damped hit/shake action for selected parts
- `Create Armor Ripple`
  creates per-frame shape keys for mesh-animation armor ripple effects around the 3D Cursor
- `Physics Power`
  scales linked recoil, impact shake, and armor ripple intensity without changing the underlying curve shape
- `Duration Scale`
  stretches or compresses role-specific linked physics tails without changing their relative preset behavior
- `Clear Physics Links`
  removes stored physics links and can detach generated GOH physics actions or clip-range metadata

## Physics Bake Workflow

The physics bake tools create normal Blender keyframes.
They are designed for pre-baked GOH animation and mesh-animation clips, not live runtime physics simulation.

Common use:

1. Select the recoil source, such as `Gun`, and the driven part, such as `Body`.
2. Make the source object active.
3. Pick a `Link Role`, such as `Body Spring`.
4. Run `Assign Physics Link`.
5. Repeat for other driven parts, such as `Antenna Whip`.
6. Activate the source object and run `Bake Linked Recoil`.

If the recoil source or its current Action has `goh_sequence_name = fire` and `goh_sequence_file = fire`, linked physics bakes inherit that sequence and export as `fire.anm` instead of the default `recoil.anm`.
When one object contains several baked ranges, `goh_sequence_ranges = fire:1-48; hit:49-96` acts as a multi-sequence table and takes priority over the single `goh_sequence_name` fallback.

Use `Physics Power` around `1.4-2.2` when you need heavier cannon recoil or more visible movement.
Use `Duration Scale` below `1.0` for snappy small-caliber motion, or above `1.0` for heavy hull recovery and antenna follow-through.
`Body Spring` is tuned for Sherman-style cannon recoil: a hard initial shove followed by a nose-up hull swing, then smaller damped pitch and side reversals.
For impact effects, use `Bake Impact Response`.
For visible surface deformation, put the 3D Cursor on the hit area and run `Create Armor Ripple` on the mesh.

See [Physics Bake Workflow](docs/PHYSICS_BAKE.md).

## MDL Model Viewer / Import

Use `File > Import > GOH Model (.mdl)` or the sidebar `GOH Export > Import GOH Model` button to load a complete GOH model for inspection.

The importer reads:

- `.mdl` skeleton hierarchy, transforms, `VolumeView`, and `LODView` references
- `.ply` visual meshes with UVs, material slots, and optional skin vertex groups
- `.mtl` material metadata and local diffuse texture files when Blender can load them
- `.vol` polyhedron collision helpers plus inline `Box`, `Sphere`, and `Cylinder` volume blocks

Recommended import settings for source-faithful SOEdit/game inspection are `Axis Conversion = None / GOH Native`, `Scale Factor = 20`, `Flip V = On`, and `Defer Basis Flip = Off`.
Use `LOD0 Only` for quick model viewing, or disable it when you want to inspect all referenced LOD meshes.
When importing `.anm` clips after a whole `.mdl`, leave animation `Axis Conversion` on `Auto / Match Imported Model` so transforms use the same coordinate space as the model.
`Defer Basis Flip` is now an explicit legacy editing option. When enabled, imported GOH root/basis mirror matrices are stored for export but displayed as a non-mirrored Blender parent. ANM import and export both convert translation and rotation deltas through the same handness compensation, including pitch parity, so hand-authored Blender animation matches SOEdit and game playback instead of being visually inverted during editing.

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
- `AnimationAuto=...`
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

The official release asset is `blender_goh_gem_exporter-1.3.0.zip`.
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
- [中文说明](README.zh-CN.md)
- [Quick Start](docs/QUICK_START.md)
- [Detailed Plugin Guide - English](docs/PLUGIN_GUIDE_EN.md)
- [Detailed Plugin Guide - Chinese](docs/PLUGIN_GUIDE_ZH-CN.md)
- [Physics Bake Workflow](docs/PHYSICS_BAKE.md)
- [Official Max Plugin Compatibility Notes](docs/OFFICIAL_MAX_PLUGIN_NOTES.md)
- [v1.3.0 Release Notes](docs/RELEASE_NOTES_v1.3.0.md)
- [v1.2.1 Release Notes](docs/RELEASE_NOTES_v1.2.1.md)

## License

This project is released under the [MIT License](LICENSE).
