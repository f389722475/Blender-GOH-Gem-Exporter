# Blender GOH GEM Exporter v1.5.0

This is a medium feature release focused on GOH `humanskin` character assets and repository maintenance.

## Added

- Dedicated humanskin import module for GOH character `.mdl` files.
- LOD0 humanskin skin views are merged into one editable skinned mesh.
- Imported humanskin meshes preserve vertex groups, weights, custom normals, and smooth shading.
- Humanskin skeleton and attachment points display in SOEdit-aligned space for practical editing.
- Regression coverage for official `ger_heer_39_at` and `us_m41_medic` humanskin samples.
- Repository-management guidance inspired by the `openai/codex` repository: `AGENTS.md`, contribution guidance, issue templates, and a PR template.

## Fixed

- Fixed incomplete humanskin imports where only part of the character skin appeared.
- Fixed scattered humanskin point display in Blender while preserving export-safe GOH rest metadata.
- Fixed humanskin skin bone index handling for round-trip export.

## Recommended Install

Install:

- `blender_goh_gem_exporter-1.5.0.zip`

Archive/source review:

- `blender_goh_gem_exporter-1.5.0-full.zip`

## Verification

- `python -m compileall blender_goh_gem_exporter`
- `python tests\smoke_test.py`
- Blender runtime regression
- Humanskin import/export regression for 5 iterations
