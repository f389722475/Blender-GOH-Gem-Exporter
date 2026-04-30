# Contributing

Thanks for helping improve `Blender GOH GEM Exporter`.

## Development Notes

- Keep the Blender addon package in `blender_goh_gem_exporter/`
- Keep regression coverage in `tests/`
- Prefer Blender-native structured fields over adding new legacy-only behavior
- Preserve compatibility with GOH, SOEdit, and common legacy Max property text where practical
- Start with an issue or reproduction note for behavior changes that affect import/export compatibility
- Keep each PR focused on one compatibility problem, feature, or documentation update
- Update documentation when a user-facing workflow, panel option, or release process changes
- Do not restore `.github/workflows/python-publish.yml`; release packaging is intentionally local

## Before Opening A Release Or PR

Run at least:

```powershell
python -X utf8 tests\smoke_test.py
```

```powershell
"D:\Steam\steamapps\common\Blender\blender.exe" -b --factory-startup --python tests\blender_runtime_test.py
```

For humanskin changes, run:

```powershell
"D:\Steam\steamapps\common\Blender\blender.exe" -b --factory-startup --python tests\regression_humanskin_import_export.py
```

For release candidates, use `tools\publish_release.ps1` from the Git mirror so validation, packaging, backup, tag creation, and GitHub release upload stay consistent.

## Pull Request Shape

- What changed?
- Why is it needed?
- How was it tested?
- Which sample files or saved `.blend` scenes were used for verification?

## Style

- Default to ASCII in source files unless the file already requires Unicode
- Keep UI wording concise and GOH-focused
- Avoid breaking old GOH scene conventions unless the new behavior is explicitly more compatible
