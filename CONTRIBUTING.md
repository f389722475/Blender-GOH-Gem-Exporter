# Contributing

Thanks for helping improve `Blender GOH GEM Exporter`.

## Development Notes

- Keep the Blender addon package in `blender_goh_gem_exporter/`
- Keep regression coverage in `tests/`
- Prefer Blender-native structured fields over adding new legacy-only behavior
- Preserve compatibility with GOH, SOEdit, and common legacy Max property text where practical

## Before Opening A Release Or PR

Run at least:

```powershell
python -X utf8 tests\smoke_test.py
```

```powershell
"D:\Steam\steamapps\common\Blender\blender.exe" -b --factory-startup --python tests\blender_runtime_test.py
```

## Style

- Default to ASCII in source files unless the file already requires Unicode
- Keep UI wording concise and GOH-focused
- Avoid breaking old GOH scene conventions unless the new behavior is explicitly more compatible
