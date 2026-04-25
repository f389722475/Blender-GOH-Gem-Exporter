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

- Prefer `NLA` strips for named clips
- Fall back to the active `Action` if no `NLA` is available
- Use shape keys or mesh animation only when topology stays stable
- Use `GOH Tools > Physics Bake Presets` for source-only recoil, linked recoil, directional fire clips, impact shake, or armor ripple
- For linked recoil, assign source-to-driven part relationships first, then run `Bake Linked Recoil`
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
- Keep `Axis Conversion = None / GOH Native`, `Scale Factor = 20`, and `Flip V = On` for SOEdit-style round trips
- Keep `LOD0 Only = On` for quick viewing
- Keep `Import Volumes = On` when checking collision helpers
- After importing the model, use `File > Import > GOH Animation (.anm)` with `Axis Conversion = Auto / Match Imported Model` so the animation reuses the model's axis and scale settings

## 6. Validate

- Open the exported files in SOEdit
- Verify part names, helper placement, collision primitives, and material mapping
- If needed, run the repository smoke and runtime tests
