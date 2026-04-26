# Quick Start

## 1. Set Up The Scene

- Put visible GOH meshes in the scene as regular mesh objects
- Use `View3D > Sidebar > GOH > GOH Presets` to assign part roles
- Use `GOH Basis` to fill in `Vehicle Name`, `Type`, `Entity Path`, `Wheelradius`, and `SteerMax`

## 2. Add Helpers

- Use `Collision Volume` presets for 3D collision helpers
- Use `Obstacle (2D)` and `Area (2D)` presets for 2D helper shapes
- Use `Dummy / Placer` and `Effect / Marker` presets for crew points, pivots, emitters, and FX markers

## 3. Animate

- Use one active `Action` timeline for physics-baked clips when you want 3ds Max-style frame ranges
- Use `NLA` strips only for manual advanced clip layering
- Use shape keys or mesh animation only when topology stays stable
- Use `GOH Tools > Physics Bake Presets` for source-only recoil, linked recoil, directional fire clips, impact shake, or armor ripple
- For linked recoil, assign source-to-driven part relationships first, then run `Bake Linked Recoil`
- For `Antenna Whip`, link the antenna to the gun/barrel source so the bake can infer the source mesh principal axis and keep the antenna swaying front-back with the cannon
- Use `Physics Power` to scale the whole physical effect after the role feels right
- Use `Duration Scale` to stretch heavy follow-through or shorten snappy light-weapon motion
- For armor ripple, place the 3D Cursor on the hit point and run `Create Armor Ripple` on the mesh

## 4. Export

- Run `GOH Tools > Validate GOH Scene` before the final export
- Use `Auto-Fill GOH Materials` if your materials use Blender image texture nodes but do not yet have `goh_*` texture fields
- Use `Assign LOD Files` when you want the exporter to write consistent `LODView` file entries
- Open `View3D > Sidebar > GOH > GOH Export`
- Export with:
  - `Axis Conversion = None / GOH Native`
  - `Scale Factor = 20`
  - `Flip V = On`

## 5. Import / View Existing MDL

- Use `File > Import > GOH Model (.mdl)` or `View3D > Sidebar > GOH > GOH Export > Import GOH Model`
- Keep `Axis Conversion = None / GOH Native`, `Scale Factor = 20`, `Flip V = On`, and `Defer Basis Flip = On` for SOEdit-style round trips
- With `Defer Basis Flip`, Blender shows a non-mirrored editing parent while export still writes the GOH basis orientation and ANM pitch parity, so hand-authored animation matches SOEdit/game direction
- Keep `LOD0 Only = On` for quick viewing
- Keep `Import Volumes = On` when checking collision helpers
- After importing the model, use `File > Import > GOH Animation (.anm)` with `Axis Conversion = Auto / Match Imported Model` so the animation reuses the model's axis and scale settings

## 6. Validate

- Open the exported files in SOEdit
- Verify part names, helper placement, collision primitives, and material mapping
- If needed, run the repository smoke and runtime tests
