# Blender GOH GEM Exporter v1.4.2

This patch release focuses on preset naming and material export stability. It keeps the v1.4.1 handedness fixes intact while tightening the everyday helper and `.mtl` round-trip paths.

## Highlights

- GOH Auto presets now generate and reserve real GOH names before Blender can append `.001` object suffixes.
- The GOH Presets panel adds a `Numbering Rule` selector for Auto presets:
  - `x1, x2`
  - `x01, x02`
- Material export adds a `Material Blend` selector with:
  - `blend none`
  - `blend test`
  - `blend blend`
- Imported material source names are preserved on export, so repeat exports overwrite stable `.mtl` files instead of producing Blender duplicate-name variants.

## Fixed

- Applying `Emit* (Auto)` and other Auto presets to existing helper sets now produces continuous GOH identifiers such as `Emit1`, `Emit2`, `Emit3`, and `Emit4`.
- Saved scenes that already contain old duplicate Auto metadata can be repaired by applying the Auto preset again.
- `.mtl` export no longer follows Blender data-block duplicate suffixes such as `.001` when the original imported material file is known.
- The default material blend mode is now explicitly `blend none`, matching the safest GOH export default.

## Validation

- Python compile and addon smoke tests.
- Blender background runtime regression.
- Saved `tests/3.blend` Auto and FRM2 ANM export regression.
- Saved `tests/3.blend` Emit Auto preset probe, confirming continuous GOH helper names.

## Release Assets

- `blender_goh_gem_exporter-1.4.2.zip`
  Blender addon install package.
- `blender_goh_gem_exporter-1.4.2-full.zip`
  Protected source, docs, tests, and regression snapshot for release review.
