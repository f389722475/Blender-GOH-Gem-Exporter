# Blender GOH GEM Exporter v1.4.1

This patch release focuses on GOH-native import display parity: Blender should show mirrored-root GOH models and their ANM clips the same way SOEdit/game do, while the original GOH matrices remain stored for export.

## Highlights

- Default `.mdl` import now enables deferred mirrored `basis` display for GOH-native round trips.
- Original mirrored `basis` rest matrices are still preserved in metadata, so export can write the source-faithful GOH hierarchy back out.
- ANM import now treats root `basis` animation keys as coordinate-frame markers when the basis is deferred, avoiding whole-vehicle parent flips.
- Mirrored-basis ANM export remains corrected, so Blender recoil/body pitch exports back into GOH mirrored animation space with the expected game direction.

## GitHub Issue Check

- Issue #3 GOH tanks samples were imported with the current fix: vanilla GOH samples now show positive Blender display basis determinants while retaining negative stored GOH rest determinants.
- The AS2 sample packs also benefit from the root-basis fix, but several of those models contain additional nested mirrored child bones. Those are a separate compatibility case and are not claimed as fully solved in this patch.
- Issue #6 describes the same Blender/game mirror mismatch class for headwear and attached emblems; this release should help when the asset is imported/exported through a full `.mdl` hierarchy with the default GOH-native settings.

## Validation

- Official T26E4 model + `fire.anm` import display-space regression.
- M60A1 import/material/animation regression, including `fire.anm` and `open_driver.anm`.
- Saved `tests/3.blend` export regression for Auto and FRM2 ANM output.
- Blender background runtime regression.
- Random vehicle import regression over 12 samples for 5 iterations.
- GitHub issue #3 sample import probe over 18 supplied MDL files.
- Python compile and addon smoke tests.

## Release Assets

- `blender_goh_gem_exporter-1.4.1.zip`
  Blender addon install package.
- `blender_goh_gem_exporter-1.4.1-full.zip`
  Protected source, docs, tests, and regression snapshot for release review.
