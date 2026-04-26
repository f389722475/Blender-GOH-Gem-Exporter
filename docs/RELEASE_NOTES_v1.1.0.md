# Blender GOH GEM Exporter v1.1.0

Release date: 2026-04-26

This important feature-fix release focuses on animation-space consistency between Blender, SOEdit, and in-game playback. It keeps Blender editing comfortable while preserving the GOH coordinate flip at export time.

## Highlights

- `Import GOH Model` now includes `Defer Basis Flip`, enabled by default for GOH-native round trips.
- Imported root `basis` mirror transforms are stored in `goh_rest_matrix_local` but displayed as a non-mirrored Blender parent.
- Hand-authored Blender animation now follows the same visible direction you see in SOEdit and the game instead of being hard to edit under a mirrored parent.
- Export still writes the required GOH `basis` orientation, so existing SOEdit/game coordinate expectations are preserved.
- New objects created under a deferred GOH basis export using their visible Blender-local transform.
- ANM export now converts stored-rest object animation deltas under a deferred GOH basis into GOH space, including the extra pitch/rotation parity compensation needed for SOEdit playback to match Blender's visible frame.
- Generated physics link-role animations under legacy mirrored imports are corrected at ANM export time.
- `SOURCE` recoil animation is left unchanged, matching cannon/barrel recoil that was already exporting correctly.
- Legacy visible-mirrored-basis compensation is limited to generated GOH physics bake actions, so ordinary manually keyed animation is not silently flipped.
- `Body Spring` now starts with a nose-up hull swing before its damped recovery, matching the preferred SOEdit-style recoil look.
- `Antenna Whip` now uses a minimum-bending-energy cubic beam curve, source-timed first kick, low-pass filtered tip target, late over-zero rebounds, and a long smooth spring tail for a less stiff second rebound and no abrupt final snap-back.

## Fixed

- Fixed linked physics role animations exporting mirrored under GOH-native imports with a negative-handed `basis`.
- Fixed deferred-basis transform animation export, including hand-keyed animation and physics-baked link roles, so exported ANM clips match Blender playback direction in SOEdit/game.
- Fixed the mismatch where Blender playback could look correct only after making the editing scene awkwardly mirrored.
- Fixed export handling for deferred-basis children that do not have stored GOH rest matrices.
- Fixed the `Antenna Whip` late-frame return by keeping the recoil impulse responsive to the source animation while preserving the role's longer damped tail.
- Fixed the late `Antenna Whip` tail becoming visually rigid after the main recoil by adding a separate low-amplitude rebound mode before the final fade.
- Added regression coverage for deferred basis import/export, deferred-basis animation pitch parity, and source-vs-linked animation direction.

## Recommended Release Assets

- `blender_goh_gem_exporter-1.1.0.zip`
  Install this in Blender through `Edit > Preferences > Add-ons > Install...`.
- `blender_goh_gem_exporter-1.1.0-full.zip`
  Full source, documentation, tests, and regression sample scenes.

## Recommended Import Settings

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`
- `Defer Basis Flip = On`

## Validation

- `python -m py_compile blender_goh_gem_exporter\__init__.py blender_goh_gem_exporter\blender_exporter.py tests\blender_runtime_test.py`
- Blender 5.1.1 background runtime regression test
- Manual `tests/2.blend` export probe for frame-8 body pitch direction, recoil source, and generated physics link direction
- Manual `tests/1.blend` antenna bake probe for smooth long-tail shape-key playback
