# Blender GOH GEM Exporter v1.2.1

Release date: 2026-04-28

This release fixes GitHub issue #3 and keeps the current collision-cage work intact.

## Highlights

- GOH `.mdl` import now applies EPLY normals as Blender custom split normals and marks imported polygons smooth.
- Default model import keeps the source `basis` mirror transform visible, so helper points, gun meshes, and child transforms match SOEdit/game space.
- `Defer Basis Flip` remains available as an explicit legacy editing option.
- ANM import and export now use matching deferred-Basis handness compensation, including translation and pitch parity.
- The automatic collision cage generator remains at the current topology level, including legal triangle/quad output, budgets up to `5000` faces, and bounded loft fitting for hulls/turrets.

## Recommended Import Settings

For source-faithful inspection and issue reproduction:

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`
- `Defer Basis Flip = Off`

For older non-mirrored Blender editing scenes, enable `Defer Basis Flip` intentionally and import ANM clips with `Axis Conversion = Auto / Match Imported Model` or the same axis mode as the model.

## Recommended Release Assets

- `blender_goh_gem_exporter-1.2.1.zip`
  Install this in Blender through `Edit > Preferences > Add-ons > Install...`.
- `blender_goh_gem_exporter-1.2.1-full.zip`
  Protected release snapshot with documentation, tests, and regression sample scenes.

## Validation

- `python -X utf8 tests\smoke_test.py`
- Blender 5.1.1 background runtime regression test.
- Blender 5.1.1 official T26E4 issue #3 import probe.
- Blender 5.1.1 `tests/2.blend` collision cage scale regression.
