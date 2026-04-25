# Blender GOH GEM Exporter v1.0.0

Release date: 2026-04-25

This is the first stable release of the Blender GOH GEM Exporter package.

## Highlights

- Full `.mdl` import for model inspection, including skeleton hierarchy, mesh references, material metadata, LOD references, volumes, obstacles, and areas.
- Export support for `.mdl`, `.ply`, `.mtl`, `.vol`, and `.anm`.
- Object/bone animation, mesh animation, and shape-key animation export workflows.
- GOH-native coordinate round-trip defaults for SOEdit and legacy Max workflows.
- Structured Blender `goh_*` metadata, plus compatibility with old MultiScript text properties.
- Primitive volume support for `Box`, `Sphere`, and `Cylinder`.
- Basis/entity metadata UI for `Type`, `Model`, `Entity Path`, `Wheelradius`, `SteerMax`, and sequence declarations.
- Weapon and texture helper panels inspired by MultiScript, with Blender-native naming and properties.
- GOH validator, material auto-fill, LOD helper, collision helper, and texture reporting tools.
- Recoil, directional fire, linked physics, impact shake, suspension bounce, track rumble, antenna whip, and armor-ripple bake tools.
- English and Chinese README files for GitHub.

## Fixed Since The Last Prerelease

- `Bake Linked Recoil` now preserves or inherits `goh_sequence_name` and `goh_sequence_file` from the recoil source/current source Action.
- Linked objects no longer let stale `recoil` Action metadata override a source sequence such as `fire`.
- Object-mode `.anm` export no longer writes the static GOH `basis` bone into animation BMAP data.

## Recommended Release Assets

- `blender_goh_gem_exporter-1.0.0.zip`
  Install this in Blender through `Edit > Preferences > Add-ons > Install...`.
- `blender_goh_gem_exporter-1.0.0-full.zip`
  Full source, documentation, tests, and regression sample scene.

## Recommended SOEdit Round-Trip Settings

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`
