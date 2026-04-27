# Blender GOH GEM Exporter v1.2.0

Release date: 2026-04-27

This release packages the current GOH Blender workflow under the `1.2.0` GitHub release line.

## Highlights

- Full `.mdl` import/export workflow for visual meshes, volumes, obstacles, areas, materials, basis metadata, and animation helpers.
- `Auto Collision Cage Volume` creates closed polyhedron helpers from selected meshes.
- Triangle and quad collision topology is legal; ngons are rejected during validation.
- A single generated collision helper can use up to `5000` faces.
- `Optimize Iterations` defaults to `12` for interactive use and can be raised manually for deeper fitting.
- Large hull/turret sources avoid runaway loft expansion and fall back to safer rounded cages when the optimizer scores them better.
- Generated helpers store review metadata: mode, source face count, final face count, target budget, margin, optimizer score, iteration count, output topology, and validation report.

## Recommended Use

1. Select the visible part you want to fit, or select a root and keep `Cage Source = Selected + Children`.
2. Start with `Face Budget = 500` and `Optimize Iterations = 8-16` for whole-vehicle work.
3. Raise iterations only for focused body, turret, or barrel selections.
4. Use `Output Topology = Tri / Quad Legal` unless you specifically need all triangles.
5. Inspect generated `_vol` helpers in wire display before export.

## Recommended Release Assets

- `blender_goh_gem_exporter-1.2.0.zip`
  Install this in Blender through `Edit > Preferences > Add-ons > Install...`.
- `blender_goh_gem_exporter-1.2.0-full.zip`
  Protected release snapshot with documentation, tests, and regression sample scenes.

## Validation

- `python -X utf8 tests\smoke_test.py`
- Blender 5.1.1 background runtime regression test.
- `tests/2.blend` scale regression for body and turret collision cage generation.
