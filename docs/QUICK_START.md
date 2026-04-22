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

## 4. Export

- Open `View3D > Sidebar > GOH > GOH Export`
- Export with:
  - `Axis Conversion = None / GOH Native`
  - `Scale Factor = 20`
  - `Flip V = On`

## 5. Validate

- Open the exported files in SOEdit
- Verify part names, helper placement, collision primitives, and material mapping
- If needed, run the repository smoke and runtime tests
