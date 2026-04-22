# Changelog

All notable changes to this project will be documented in this file.

## 0.8.0-pre1 - 2026-04-22

### Added

- `GOH Basis` panel for `Vehicle Name`, `Type`, `Entity Path`, `Wheelradius`, `SteerMax`, and legacy animation lines
- `GOH Tools` helpers for transform block selection, weapon helper shortcuts, and texture reporting
- Template-family filtering for `Generic`, `Tank`, `Car`, `Cannon`, and `Weapon`
- Inline primitive collision export for `Box`, `Sphere`, and `Cylinder`
- Legacy Max compatibility for `Poly`, `CommonMesh`, `Volume`, `ID`, `IK*`, `Transform`, and Basis metadata
- `MIT` license and GitHub-ready project documentation

### Changed

- Normalized GOH preset naming to English GOH / MultiScript style labels
- Tuned SOEdit round-trip defaults to `Axis=None`, `Scale=20`, `Flip V=On`
- Improved root transform handling for GOH-native basis orientation
- Reworked repository documentation for prerelease packaging and installation

### Fixed

- SOEdit round-trip orientation mismatch for single-root visual meshes with Blender-side correction rotation
- Material UV round-trip issues caused by wrong export defaults
- UI label translation drift for GOH helper buttons such as `Poly`

## 0.7.0 - 2026-04-22

### Added

- Primitive volume support and extended GOH helper presets
- Basis metadata emission into exported `mdl`
- Additional test coverage for GOH-specific metadata and helper workflows
