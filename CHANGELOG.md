# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- No changes yet.

## 1.5.1 - 2026-05-01

### Added

- Added an Eight Fire Directions physics-bake preset with diagonal `fire_fl`, `fire_bl`, `fire_br`, and `fire_fr` clips.
- Added a fire trigger volume generator that creates `recoil_gun_*_vol` pie-slice GOH volumes under `basis` and a `gun_recoil` point under `turret`.
- Added `Body Sway Strength` and `Antenna Sway Strength` sliders for quick rebake tuning without reassigning physics links.
- Added an `Antenna Mount` selector so directional bakes can treat whip antennas as either body-mounted or turret-mounted.

### Fixed

- Fixed `Bake Directional Set` so it rebuilds fire clips from the scene start frame instead of appending from the current viewport frame.
- Fixed directional barrel and turret-scoped linked clips so every fire direction uses the same fixed `X/-X` recoil stroke instead of sliding diagonally or sideways.
- Fixed directional fire body response so the hull first recoils opposite the fire direction with a nose-up kick, then returns forward/down.
- Fixed Antenna Whip directional polarity and axis selection so every fire direction uses the fixed gun `X/-X` sway and the free antenna tip initially swings toward `+X` when the gun and hull recoil backward.
- Fixed legacy Antenna Whip FRM2 export so saved generated whip shape keys are sampled directly even when older `.blend` files are missing `goh_physics_role`, preventing later directional clips from stretching the antenna mesh.
- Fixed repeated directional antenna rebakes so all eight whip segments, including `fire_fr`, keep clean shape-key curves.
- Fixed generated `gun_recoil` placement so its basis-space Z position stays aligned with the `recoil_gun_front_vol` trigger plane while remaining a `turret` child.
- Fixed repeated fire-trigger generation so replaced `recoil_gun_*_vol` meshes remain parented and aligned to `basis` instead of drifting toward `turret`.

### Changed

- Replaced the old Six Local Axes directional bake option with Eight Fire Directions and aligned fire directions to the GOH vehicle horizontal axes: `front/back/left/right = +X/-X/+Y/-Y`.

## 1.5.0 - 2026-05-01

### Added

- Added a dedicated humanskin import module for GOH character `.mdl` files.
- Humanskin LOD0 skin views are merged into a complete editable skinned mesh while preserving vertex groups, weights, source smoothing, and GOH custom normals.
- Added humanskin import/export regression coverage for the `ger_heer_39_at` and `us_m41_medic` official samples.
- Added repository-management guidance inspired by the `openai/codex` layout: agent instructions, contribution flow, issue templates, and a PR template.

### Fixed

- Fixed humanskin skeleton and attachment point display so points line up with SOEdit-style placement instead of scattering around the imported body.
- Fixed humanskin round-trip skin bone indexing so exported `skin.ply` keeps the real GOH bone table instead of shifting weights by one slot.

### Verified

- Ran Python compile and addon smoke tests.
- Ran the Blender runtime regression.
- Ran the humanskin import/export regression for 5 iterations.

## 1.4.2 - 2026-04-30

### Added

- Added a GOH preset numbering rule selector for Auto presets, with `x1, x2` and `x01, x02` formats.
- Added an export-side material blend preset selector for `blend none`, `blend test`, and `blend blend`.

### Fixed

- Fixed Auto GOH presets so generated names reserve real GOH identifiers instead of letting Blender create `.001` object suffixes.
- Fixed legacy/broken Auto preset data repair coverage for saved `tests/3.blend`, including duplicate `Emit1` helper metadata.
- Fixed material export naming so imported `.mtl` source names are preserved and repeat exports overwrite stable filenames instead of creating `*.001.mtl` variants.

### Verified

- Ran Python compile and addon smoke tests.
- Ran the Blender runtime regression.
- Ran the saved `tests/3.blend` Auto/FRM2 export regression.
- Probed the saved `tests/3.blend` Emit Auto preset path and confirmed `Emit1/Emit2/Emit3/Emit4` GOH names.

## 1.4.1 - 2026-04-29

### Fixed

- Changed default GOH-native `.mdl` import display to defer mirrored root `basis` transforms, so Blender shows the same model handedness and helper placement expected in SOEdit/game while preserving the original mirrored basis metadata for export.
- Fixed ANM import for deferred root `basis` clips that include their own coordinate-frame marker, preventing parent-space flips from moving the whole vehicle away from the imported rest pose.
- Kept mirrored-basis ANM export correction aligned with the new import default, so Blender-authored recoil/body pitch exports back into GOH mirrored animation space.

### Verified

- Imported the GitHub issue #3 GOH tanks sample pack; all GOH vanilla samples now import with non-mirrored Blender display `basis` and preserved mirrored GOH rest metadata.
- Imported the issue #3 AS2 sample packs to confirm root-basis mirroring is covered; models with additional nested mirrored child bones remain tracked as a separate compatibility case.
- Ran T26E4 official `fire.anm`, M60A1 import/material/animation, `tests/3.blend` export, Blender runtime, smoke, and random vehicle import regressions.

## 1.4.0 - 2026-04-29

### Added

- Added a PhysX-inspired inertial bake core with solver-space resolution, source-motion acceleration sampling, mass/inertia-aware semi-implicit integration, D6-lite axis limits, force clamps, substeps, and end fade.
- Added `Solver Space`, `Substeps`, `Force Limit`, and `End Fade` controls to linked physics bake settings, with matching object custom properties for stored links.
- Added regression coverage for recoil-force direction, rotated vehicle solver-space invariance, mass scaling, clamp safety, FPS/substep stability, and stale Blender addon module loading.

### Changed

- Migrated non-antenna linked recoil roles to the new inertial solver while preserving the existing Antenna Whip beam/late-rebound mesh bake path.
- Treats source recoil displacement as a same-direction force proxy for rigid linked bodies, while keeping flexible antenna deformation as root-anchored relative inertial lag.
- Added a subtle Body Spring crank-style pitch layer so heavy vehicles lift, dip back, and rebound more naturally after firing.
- Smoothed the Body Spring crank layer over the longer recoil clip and flipped Antenna Whip free-tip bend so antennas lag opposite the anchored recoil motion while preserving the late rebound shape.

### Verified

- Ran the saved `tests/2.blend` inertial physics regression for 5 iterations.
- Ran the inertia solver math regression for 5 iterations.
- Ran Blender runtime, M60A1 ANM import, Python compile, and addon smoke tests.
- Ran the 12-sample random vehicle import regression for 5 iterations.

## 1.3.2 - 2026-04-29

### Fixed

- Fixed ANM import for the default source-faithful mirrored `basis` path so child rotations are corrected when the parent basis remains mirrored in Blender.
- Added direct frame-12 pitch regressions for M60A1 `fire.anm` and a reusable ANM pitch probe for saved `.blend` scenes.

### Verified

- Reimported `fire.anm` into `tests/m60a1.blend`: frame 12 `body` pitch is `-1.111113`.
- Reimported Conqueror `fire_front.anm` into `tests/conquermk2.blend`: frame 12 `body` pitch is `-1.716000`.
- Ran Blender M60A1 import/material/animation regression, Blender runtime regression, Python smoke tests, and 12-sample random vehicle import regression for 5 iterations.

## 1.3.1 - 2026-04-28

### Fixed

- Fixed GEM material import preview mapping so diffuse, normal, and specular textures drive Blender materials without inventing unsupported AO or metallic channels.
- Fixed ANM import handedness handling for GOH-native mirrored basis chains by preserving the imported MDL rest orientation while applying animation translation deltas.

### Verified

- Added and ran the M60A1 import/animation regression against the WTREBUILD sample vehicle.
- Added and ran the 12-sample random vehicle import regression for 10 iterations.

## 1.3.0 - 2026-04-28

### Changed

- Split the monolithic Blender addon module into focused export, import, collision, physics, preset, and helper modules while preserving the existing Blender entry points.
- Kept the topology-aware collision cage generator and physics bake behavior covered by smoke, Blender runtime, issue #3, and `tests/2.blend` regression tests.
- Updated release packaging so the addon zip includes the full modular package, with the two internal algorithm modules protected in the local release build.

## 1.2.1 - 2026-04-28

### Added

- Added the current automatic `Auto Collision Cage Volume` workflow for GOH `.vol` helper authoring.
- Added topology-aware triangle/quad validation: triangles and quads are legal, ngons are rejected, and degenerate faces are reported.
- Added per-helper collision budgets up to `5000` faces.
- Added configurable `Optimize Iterations`, defaulting to `12` for responsive interactive use.
- Added generated-helper metadata for optimizer score, iteration count, output topology, face budget, source face count, final face count, and validation diagnostics.
- Added `tests/check_auto_cage_scale_2blend.py` to guard against runaway hull/turret/body cage expansion in `tests/2.blend`.
- Added `tests/import_issue3_t26e4_probe.py` to cover issue #3 with the official GOH T26E4 sample model.

### Changed

- Large body and turret sources now use bounded loft expansion and early template exploration, so low-iteration fitting can choose safer rounded cages instead of producing oversized loft cages.
- GOH model import now applies EPLY vertex normals as Blender custom split normals and marks imported polygons smooth, restoring source smoothing on barrels, wheels, armor curves, and other rounded parts.
- Default GOH model import no longer defers the mirrored Basis transform. This keeps child helpers, gun meshes, and vanilla model hierarchy positions faithful to the source file; the old deferred mode remains available as an explicit import option for round-trip editing scenes.
- Release packages now use a smaller loader plus binary runtime resource payload instead of putting large encoded payload strings directly in visible `.py` files.

### Verified

- `python -X utf8 tests\smoke_test.py`
- Blender 5.1.1 background runtime regression.
- Blender 5.1.1 official T26E4 issue #3 import probe.
- Blender 5.1.1 `tests/2.blend` collision cage scale regression.
