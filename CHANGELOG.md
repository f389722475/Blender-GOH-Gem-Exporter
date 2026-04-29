# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

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
