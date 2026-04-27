# Changelog

All notable changes to this project will be documented in this file.

## 1.2.0 - 2026-04-27

### Added

- Added the current automatic `Auto Collision Cage Volume` workflow for GOH `.vol` helper authoring.
- Added topology-aware triangle/quad validation: triangles and quads are legal, ngons are rejected, and degenerate faces are reported.
- Added per-helper collision budgets up to `5000` faces.
- Added configurable `Optimize Iterations`, defaulting to `12` for responsive interactive use.
- Added generated-helper metadata for optimizer score, iteration count, output topology, face budget, source face count, final face count, and validation diagnostics.
- Added `tests/check_auto_cage_scale_2blend.py` to guard against runaway hull/turret/body cage expansion in `tests/2.blend`.

### Changed

- Large body and turret sources now use bounded loft expansion and early template exploration, so low-iteration fitting can choose safer rounded cages instead of producing oversized loft cages.
- Release packages now use a smaller loader plus binary runtime resource payload instead of putting large encoded payload strings directly in visible `.py` files.

### Verified

- `python -X utf8 tests\smoke_test.py`
- Blender 5.1.1 background runtime regression.
- Blender 5.1.1 `tests/2.blend` collision cage scale regression.
