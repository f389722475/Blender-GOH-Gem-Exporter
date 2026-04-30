# Repository Agent Notes

These notes are for Codex or any maintainer working in this repository.

## Project Shape

- The Blender addon package lives in `blender_goh_gem_exporter/`.
- Format parsing and writing lives in `blender_goh_gem_exporter/goh_core.py` and focused modules under `blender_goh_gem_exporter/formats/`.
- Import and export orchestration lives under `blender_goh_gem_exporter/importers/` and `blender_goh_gem_exporter/export/`.
- Regression probes live in `tests/`.
- Release notes and user-facing workflow docs live in `docs/`.

## Change Discipline

- Keep feature work focused on GOH/GEM compatibility and Blender editing workflows.
- Prefer small focused modules over growing already-large files when a feature has its own format rules.
- Preserve source-faithful GOH metadata for export even when Blender display transforms are adjusted for editing.
- Do not restore `.github/workflows/python-publish.yml`; releases are local, protected-package releases.
- Do not overwrite protected release-loader files in the Git mirror with unprotected development copies.

## Validation

Run targeted tests for the area you changed. For release candidates, run at least:

```powershell
python -m compileall blender_goh_gem_exporter tests
python tests\smoke_test.py
"D:\Steam\steamapps\common\Blender\blender.exe" --background --factory-startup --python tests\blender_runtime_test.py
```

For humanskin changes, also run:

```powershell
"D:\Steam\steamapps\common\Blender\blender.exe" --background --factory-startup --python tests\regression_humanskin_import_export.py
```

## Release Notes

- Update `CHANGELOG.md`, `README.md`, `README.zh-CN.md`, and `docs/RELEASE_NOTES_vX.Y.Z.md`.
- Build release zips from the Git mirror with protected files.
- Back up the unencrypted development tree into `Blender GOH Gem Exporter Unlock` before publishing.
