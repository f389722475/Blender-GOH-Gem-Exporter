# Changelog

All notable changes to this project will be documented in this file.

## 1.1.0 - 2026-04-26

### Added

- Added `Defer Basis Flip` to `Import GOH Model`, enabled by default for GOH-native imports. Imported root `basis` mirror transforms are now stored in `goh_rest_matrix_local` for export while Blender displays a non-mirrored editing parent, keeping hand-authored animation direction consistent with SOEdit and in-game playback.
- Added export handling for new objects parented under a deferred GOH basis, so hand-created Blender parts keep their visible Blender-local transform while the exported MDL still writes the GOH basis orientation.
- Added ANM export-space conversion for stored-rest objects under a deferred GOH basis. Blender keeps the visible editable animation direction, while exported transform deltas and pitch parity are mirrored into GOH space so SOEdit/game playback matches Blender.
- Added runtime regression coverage for deferred-basis import/export, deferred-basis animation pitch parity, mirrored-basis physics link export, and source-vs-linked animation direction.
- Tuned the `Body Spring` linked-physics preset so its dominant early hull swing is nose-up, matching the more natural SOEdit-style recoil result.
- Tuned `Antenna Whip` mesh deformation with a minimum-bending-energy cubic beam curve blended with the first cantilever mode, so the antenna forms one smooth elastic arc instead of a segmented rod or snake-like wave.

### Fixed

- Fixed mirrored export of generated physics link-role animations under legacy imported GOH `basis` objects with negative handedness.
- Kept `SOURCE` recoil animation unchanged during mirror compensation, matching cannon/barrel recoil behavior that was already correct.
- Limited the legacy visible-mirrored-basis compensation to generated GOH physics bake actions (`goh_recoil_*`, `goh_linked_recoil_*`, etc.) so ordinary hand-keyed Blender animations are not silently flipped just because an object has link-role metadata.
- Smoothed `Antenna Whip` rebound timing by separating the fast source-recoil kick from its longer spring tail, low-pass filtering the tip target, and using a quintic end fade so late frames ease back to rest instead of snapping.
- Preserved small late `Antenna Whip` over-zero rebounds through the long tail, preventing frames after the main cannon recoil from becoming a stiff one-way fade.

## 1.0.1 - 2026-04-26

### Fixed

- `Antenna Whip` linked physics now bakes mesh antennas as anchored shape-key mesh animation when possible, auto-adds lengthwise bend segments for sparse antenna meshes, detects the antenna principal axis, and uses a Verlet/PBD-style constrained spine with tangent-rotated sections so the bend travels along the antenna instead of behaving like a straight rod.
- Re-baking `Antenna Whip` now clears generated antenna shape keys before topology subdivision, so changed `Antenna Root Anchor` and `Antenna Bend Segments` values actually take effect on repeated bakes.
- `Antenna Root Anchor` now supports negative virtual-root values for moving the bend start below the visible mesh bottom while keeping the bottom vertices pinned.
- `Antenna Whip` linked recoil now follows the source recoil frame count, so a 30-frame cannon recoil drives the antenna bend and rebound inside that same response window instead of delaying most motion into the old long tail.
- Tuned `Antenna Whip` to use a first-mode cantilever beam response with constrained spine sampling, which removes the snake-like S-curve while keeping a visible rooted whip arc and early cannon-shot impulse.
- Increased `Antenna Whip` muzzle impulse and lowered modal damping so the antenna now performs multiple natural left-right rebounds within the recoil clip.
- Smoothed `Antenna Whip` playback by replacing hard tip clamps with soft limiting, using linear shape-key interpolation, and trimming static shape-key tails after the antenna response ends.
- `Antenna Whip` now infers the linked source mesh principal axis for elongated gun/barrel sources, keeping antenna sway aligned with the cannon and vehicle front-back direction instead of accidentally swinging sideways from a mismatched recoil axis.

## 1.0.0 - 2026-04-25

### Added

- Added the first stable release package layout with addon-only and full-source release assets.
- Added a Chinese README and stable v1.0.0 release notes for bilingual GitHub presentation.
- Added `.mdl` import visualization for `Obstacle` and `Area` helpers, including `Obb2`, `Circle2`, and `Polygon2` shapes.
- Added `GOH_Export_Manifest.json` with exported file hashes, export settings, and object/animation counts.

### Fixed

- Physics bake now appends clip ranges on the active Action timeline instead of replacing the previous bake, matching the 3ds Max workflow where one dense timeline is sliced by frame ranges such as `fire 1-48` and `hit 49-96`.
- `Bake Linked Recoil` now preserves or inherits custom `goh_sequence_name` / `goh_sequence_file` values such as `fire`, instead of falling back to `recoil.anm`.
- Linked physics objects ignore stale old linked Action names during a new source-driven bake, so previous `recoil` metadata cannot override the current source sequence.
- Imported primitive cylinder volumes now restore `goh_volume_axis=z` for safer round-trip export.
- Scene validation now warns about missing UV maps, empty / zero-area meshes, invalid shape helpers, missing cylinder axes, and overlapping multi-range GOH sequence metadata.

## 0.14.0-pre6 - 2026-04-25

### Fixed

- Object-mode `.anm` export no longer writes the static GOH `basis` bone into animation BMAP data. This matches official clips such as `m4a3e2_76/fire.anm` and prevents SOEdit static view and playback view from using different root/basis poses.
- Added a runtime regression check that object-mode `.anm` files do not override the static MDL basis transform.

## 0.14.0-pre5 - 2026-04-25

### Fixed

- Fixed whole-scene export after importing an `.mdl`: `Selection Only` off now scans the full scene instead of only the active collection, and ignores non-GOH object types such as cameras and lights.
- Fixed GOH-native `basis` round-trips so the imported basis orientation is used as the parent reference instead of being baked a second time into root bones like `body`.
- Imported model objects now store their rest local matrix, keeping static `.mdl` export stable even after physics or imported animation actions are active in Blender.
- Primitive/poly volume export now resolves object-mode bone references through the exported object bone map, preventing imported volumes from inheriting the wrong basis-space transform.
- `Bake Linked Recoil` now marks linked response actions with the `recoil` sequence metadata and keeps linked parts fully at rest during their delay frames, including jitter.

### Added

- Runtime regression coverage for GOH basis helper round-trips and linked-recoil delay rest frames.
- Real `m4a3e2_76` regression coverage for import -> linked physics bake -> `.mdl`/`.anm` export.

## 0.14.0-pre4 - 2026-04-25

### Changed

- Reworked `Body Spring` linked physics into a Sherman-inspired underdamped pendulum response with multiple progressive rotation reversals instead of a single elastic return.
- Strengthened `Suspension Bounce` with a clearer compression/rebound tail and longer default recovery.
- Linked recoil and impact-response bakes now force linear interpolation on dense per-frame physics keys, preserving the sampled spring curve more faithfully.

### Added

- Runtime checks that `Body Spring` produces damped rotation reversals, lateral pendulum follow-through, and decaying late motion.

## 0.14.0-pre3 - 2026-04-25

### Fixed

- `Import GOH Animation (.anm)` now defaults to `Auto / Match Imported Model`, so animations imported after a whole `.mdl` model reuse the model's axis conversion and scale metadata instead of rotating into a different coordinate space.
- Imported `.mdl` objects now store axis, scale, and UV flip metadata for later animation and review tools.
- Animation object targeting now prefers imported `.mdl` objects when duplicate bone names exist in the scene.

## 0.14.0-pre2 - 2026-04-25

### Fixed

- Treat official/mod `MROR` EPLY trailer markers as supported zero-length mesh metadata, avoiding noisy import warnings for smoke launchers and similar helper meshes.

## 0.14.0-pre1 - 2026-04-25

### Added

- `Import GOH Model (.mdl)` operator for loading a complete model into Blender for inspection
- Text parser for `.mdl` skeleton, `VolumeView`, `LODView`, shape helper, and volume blocks
- Binary readers for GOH `EPLY` meshes and `EVLM` polyhedron volumes
- `.mtl` reader that restores GOH material metadata and can attach local diffuse textures when Blender can load them
- Runtime round-trip coverage that exports a model, imports it back, and verifies visual mesh, material, and primitive volume reconstruction

### Changed

- Sidebar import/export panel now includes both whole-model import and animation import

## 0.13.0-pre1 - 2026-04-25

### Added

- `Duration Scale` global timing multiplier for linked physics and impact response bakes
- Role-specific default duration tails: long antenna whip, medium hull/suspension recovery, short accessory and track vibration
- Runtime checks for role duration ordering, duration-scaled clip length, and end-frame settling

### Changed

- Linked recoil and directional recoil clips now extend to the longest driven role while the source recoil can recover earlier and hold cleanly
- Impact responses now use role-specific duration scaling and a forced end fade
- Physics bake docs now include the practical math model and references for PBD, XPBD, Projective Dynamics, and reduced/modal dynamics

## 0.12.0-pre1 - 2026-04-25

### Added

- `Physics Power` global intensity multiplier for linked recoil, impact shake, and armor ripple
- `Suspension Bounce` link role for vehicle movement bounce, pitch, and recovery
- `Track Rumble` link role for tracks, wheels, bogies, and road-wheel chatter
- Runtime checks that physics roles produce distinct motion profiles and auto-store role defaults

### Changed

- Link-role presets now use stronger role-specific defaults by default
- `Assign Physics Link` now writes role defaults automatically when generic UI values are still unchanged
- Linked physics responses now use analytic spring/damper helpers, quintic smoothing, and modal oscillator blends for stronger and more distinct motion
- Impact responses now reuse the same role-specific motion profile instead of a single generic shake

## 0.11.0-pre1 - 2026-04-24

### Added

- `Bake Directional Set` for fire-front/back/left/right NLA clip generation
- `Bake Impact Response` for damped shell-hit or impact shake actions
- `Create Armor Ripple` for per-frame shape-key mesh animation around the 3D Cursor
- `Load Role Defaults` and `Clear Physics Links` helper operators
- Runtime coverage for directional recoil, impact response, armor ripple, and physics cleanup

### Changed

- Mesh-animation exports now preserve loop-vertex layout for shape-key animated meshes so local deformation keeps a stable GOH vertex stream
- Mesh-animation import matching now uses the same stable layout rule
- Blender 5 layered Action f-curve access is handled through a compatibility helper
- Custom property reads now safely skip Blender data blocks that do not support ID properties

## 0.10.0-pre1 - 2026-04-24

### Added

- Linked physics-bake recoil workflow built on top of the existing recoil action generator
- `Assign Physics Link` operator for storing `goh_physics_source`, `goh_physics_role`, `goh_physics_weight`, and related bake controls
- `Bake Linked Recoil` operator that bakes source recoil plus linked body spring, antenna whip, accessory jitter, and follower responses into regular keyframes
- Damped spring response controls for linked parts: weight, delay, frequency, damping, jitter, and rotation
- Runtime test coverage for source recoil driving separate body and antenna linked responses

### Changed

- Expanded `Physics Bake Presets` into a small linked animation-bake framework suitable for GOH pre-baked effects

## 0.9.0-pre1 - 2026-04-24

### Added

- `GOH Validator` report tool for Basis, duplicate names, helper metadata, LOD entries, volume kinds, material texture fields, missing texture paths, and unapplied mesh scale
- Material auto-fill tool that infers `goh_diffuse`, `goh_bump`, `goh_specular`, `goh_lightmap`, `goh_mask`, and related fields from Blender image texture names
- LOD helper that writes `goh_lod_files` and optional `{OFF}` metadata for selected visual meshes
- Collision helper that creates GOH volume objects from selected mesh bounds
- Physics bake preset that creates a baked local-axis recoil action and optional GOH sequence metadata

### Changed

- Expanded `GOH Tools` into validation, material, LOD, collision, and physics-bake sections
- Added Blender runtime coverage for the new tools

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
